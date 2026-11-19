"""Smoke test of the Ali Cook page in a phone-sized browser.

Run:  pip install playwright && playwright install chromium && python tests/ui_test.py
The Android bridge (window.AliCook) is replaced by a stub that records calls.
Exits with a non-zero code on the first failed check or on any JavaScript error.
"""
import os, sys
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'file://' + os.path.join(ROOT, 'app', 'src', 'main', 'assets', 'index.html')
STUB = """window.__calls=[];window.AliCook={share(t){__calls.push('share')},
startTimer(s){__calls.push('timer '+s)},startTimerText(s,t){__calls.push('timerText '+s)},cancelTimer(){__calls.push('cancel')},
startTimerId(i,s,t){__calls.push('start '+i+' '+s)},cancelTimerId(i){__calls.push('cancel '+i)},
exportFile(n,t){__calls.push('export '+n.slice(0,14)+' '+t.length)},importFile(){__calls.push('import')},
keepScreenOn(v){},httpRequest(){},openUrl(){}}"""
errors, failed = [], []


def check(name, ok, detail=''):
    print(('ok   ' if ok else 'FAIL ') + name + (' — ' + str(detail) if detail != '' else ''))
    if not ok:
        failed.append(name)


def main():
    with sync_playwright() as p:
        channel = os.environ.get('UI_TEST_CHANNEL')
        b = p.chromium.launch(channel=channel, args=['--no-sandbox']) if channel else p.chromium.launch(args=['--no-sandbox'])
        pg = b.new_context(viewport={'width': 360, 'height': 740}).new_page()
        pg.on('pageerror', lambda e: errors.append(str(e)[:300]))
        pg.on('console', lambda m: errors.append(m.text[:300]) if m.type == 'error' else None)
        pg.add_init_script(STUB)
        pg.goto(URL)
        pg.wait_for_selector('#app [data-id]')
        ev = pg.evaluate

        n = ev('recipes.length')
        check('catalog loaded', n > 1000, n)
        check('every recipe has steps in 3 languages', ev("recipes.every(r=>r.steps.length&&r.steps.length===r.steps_kk.length&&r.steps.length===r.steps_en.length)"))
        check('every recipe has a dish type', ev("recipes.every(r=>DISH_TYPES.includes(r.type))"))
        check('every recipe has protein/fat/carbs', ev("recipes.every(r=>Array.isArray(r.pfc)&&r.pfc.length===3)"))
        check('every photo file exists', all(os.path.exists(os.path.join(ROOT, 'app/src/main/assets', ph)) for ph in ev("recipes.map(r=>r.photo).filter(p=>p&&!/^https?:/.test(p))")))
        check('header is compact', ev("document.querySelector('header').offsetHeight") < 140)

        # search, typo correction, filters
        pg.fill('#search', 'борш'); pg.wait_for_timeout(200)
        check('typo "борш" finds borscht', ev("[...document.querySelectorAll('#app [data-id] b')].some(b=>/борщ/i.test(b.textContent))"))
        pg.fill('#search', ''); pg.wait_for_timeout(100)
        pg.click('#flt-btn')
        pg.select_option('#category', 'Супы'); pg.select_option('#cuisine', 'Казахская кухня'); pg.wait_for_timeout(200)
        soups = ev("[...document.querySelectorAll('#app [data-id]')].length")
        check('type + cuisine filter (Kazakh soups)', 0 < soups < 40, soups)
        check('filter button counts filters', '(2)' in pg.inner_text('#flt-btn'))
        pg.select_option('#category', ''); pg.select_option('#cuisine', 'Индийская кухня'); pg.wait_for_timeout(200)
        check('new world cuisine is filterable (Indian)', ev("[...document.querySelectorAll('#app [data-id]')].length") >= 8)
        check('new cuisines are listed', ev("['Тайская кухня','Испанская кухня','Польская кухня','Перуанская кухня'].every(c=>[...document.querySelectorAll('#cuisine option')].some(o=>o.value===c))"))
        pg.select_option('#cuisine', ''); pg.click('#flt-btn')

        # products
        pg.click('#products-tab'); pg.wait_for_timeout(200)
        check('product groups shown', ev("document.querySelectorAll('.pgroups [data-g]').length") >= 9)
        for n in ('картофель', 'лук', 'говядина'):
            pg.fill('#product-search', n); pg.wait_for_timeout(80)
            pg.locator('#product-grid [data-product="%s"]' % n).click()
        pg.fill('#product-search', ''); pg.click('#show-matches'); pg.wait_for_timeout(300)
        m = ev("[document.querySelectorAll('#app [data-id]').length, document.querySelectorAll('#app [data-id] img.thumb').length]")
        check('product matches show photos', m[0] > 0 and m[1] == m[0], m)
        ev("selected.clear();saveProducts();filterMode=false;render()")
        pg.click('#products-tab'); pg.wait_for_timeout(200)
        pg.click('#recipes-tab')

        # recipe view
        pg.fill('#search', 'суп харчо'); pg.wait_for_timeout(200)
        pg.locator('#app [data-id]').first.click(); pg.wait_for_timeout(300)
        txt = pg.inner_text('#app')
        check('recipe shows calories and protein/fat/carbs', ev("!!document.querySelector('.kcal')&&!!document.querySelector('.pfc')"))
        check('ingredients use kitchen units', ev("/л|шт|ст\\. л|зубчик/.test(document.querySelector('#app .scaler+ul').innerText)"))
        check('steps have timer buttons', ev("document.querySelectorAll('#app ol .tbtn').length") > 0)

        # timers: start from the recipe, keep running outside it
        pg.locator('#app ol .tbtn').first.click(); pg.wait_for_timeout(200)
        check('timer chip appears', ev("document.querySelectorAll('#tbar .tchip').length") == 1)
        check('native timer started with id', any(c.startswith('start 1 ') for c in ev('__calls')), ev('__calls'))
        pg.click('#cook-btn'); pg.wait_for_timeout(200)
        check('cooking mode opens', ev("!!document.getElementById('cook')"))
        pg.click('#ck-next'); pg.wait_for_timeout(100); pg.click('#ck-x'); pg.wait_for_timeout(200)
        check('timer survives leaving cooking mode', ev("timers.length") == 1)
        ev("appBack()"); pg.wait_for_timeout(200)
        check('timer visible on the list', ev("view==='list'&&document.querySelectorAll('#tbar .tchip').length===1"))
        ev("window.onNativeTimerDone(1)"); pg.wait_for_timeout(200)
        check('finished timer is marked', ev("document.querySelector('#tbar .tchip').classList.contains('done')"))
        pg.click('#tbar .tchip [data-tx]'); pg.wait_for_timeout(200)
        check('timer dismissed', ev("timers.length") == 0 and 'cancel 1' in ev('__calls'))
        pg.fill('#search', ''); pg.wait_for_timeout(100)

        # step time parsing
        d = ev("""['Варите 2–3 часа.','Обжарьте 10 минут, затем тушите 20 минут.','Запекайте 1 час 30 минут.','Разделите на 2 части.'].map(stepDurations)""")
        check('durations parsed', d == [[180], [10, 20], [90], []], d)

        # weekly menu
        ev("newWeek();renderWeek()"); pg.wait_for_timeout(300)
        check('weekly menu has 7 days with calories', ev("document.querySelectorAll('.wday').length===7&&document.querySelectorAll('.wday h3 small').length===7"))
        check('dinners are main courses', ev("week.days.every(d=>recipes.find(r=>r.id===d.wd).type==='Вторые блюда')"))
        ev("goList()")

        # shopping list and backup
        pg.fill('#search', 'оладьи'); pg.wait_for_timeout(200)
        pg.locator('#app [data-id]').first.click(); pg.wait_for_timeout(200)
        pg.click('#fav-btn'); pg.click('#shop-add'); ev("goList()"); pg.fill('#search', '')
        pg.click('#shop-tab'); pg.wait_for_timeout(200)
        check('shopping list has items', ev("document.querySelectorAll('.shop-item').length") > 0)
        ev("goList()"); pg.click('#set-btn'); pg.wait_for_timeout(200)
        pg.click('#file-save'); pg.wait_for_timeout(100)
        check('backup file export requested', any(c.startswith('export alicook-backup') for c in ev('__calls')))
        pg.click('#exp-btn'); backup = pg.input_value('#imp-text')
        ev("localStorage.removeItem('alicook-favs')")
        ev("window.onBackupFile(%s)" % repr(backup)); pg.wait_for_timeout(1500)
        check('backup restores favourites', ev("localStorage.getItem('alicook-favs')") not in (None, '[]'))

        # languages
        for lang in ('kk', 'en', 'ru'):
            pg.wait_for_selector('#app [data-id]')
            pg.click('[data-lang=%s]' % lang); pg.wait_for_timeout(200)
            pg.locator('#app [data-id]').nth(3).click(); pg.wait_for_timeout(200)
            check('recipe opens in ' + lang, ev("view==='recipe'&&document.querySelectorAll('#app ol li').length>0"))
            ev("goList()"); pg.wait_for_timeout(100)

        # back button
        pg.locator('#app [data-id]').nth(1).click(); pg.wait_for_timeout(200)
        check('back returns to the list', ev("appBack()") is True and ev("view") == 'list')
        b.close()

    check('no JavaScript errors', not errors, errors[:5])
    if failed:
        print('\n%d check(s) failed: %s' % (len(failed), ', '.join(failed)))
        sys.exit(1)
    print('\nAll checks passed')


if __name__ == '__main__':
    main()

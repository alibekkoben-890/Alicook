# Ali Cook — Android MVP

647 рецептов (RU / ҚАЗ / EN), включая итальянскую, грузинскую, казахскую кухню и десерты: поиск, категории, подбор блюд по продуктам, пошаговые рецепты, офлайн-доступ. У всех блюд есть фото (Pixabay, Wikimedia Commons, Openverse/Flickr и собственные), встроенные в APK; если на фото похожее блюдо, это подписано; авторы и лицензии — в PHOTO_SOURCES.md.

## Сборка APK
1. Откройте эту папку в Android Studio с установленным Android SDK 35 и JDK 17.
2. Дождитесь Gradle Sync.
3. Выберите Build → Build Bundle(s) / APK(s) → Build APK(s).
4. Файл APK появится в app/build/outputs/apk/debug/.

В архиве нет Gradle Wrapper и готового APK: Android Studio использует установленный Gradle или предложит настройку.
Калорийность приблизительная на весь рецепт. Для публикации потребуется тестирование и настройка современных Android API.

Проверка 05.11.2026: 165 записей; данные встроены в index.html, чтобы работать в WebView без fetch(file://). Указана версия Android Gradle Plugin 8.7.3. APK в этой среде не собирался из-за отсутствия Android SDK и Gradle.

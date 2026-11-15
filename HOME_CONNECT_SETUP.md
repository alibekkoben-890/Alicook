# Home Connect (Bosch, Siemens, Neff): настройка для владельца приложения

Пользователи Ali Cook подключают духовку одной кнопкой «🔌 Подключить духовку»:
входят в свой аккаунт Home Connect и нажимают «Разрешить». Регистрироваться
разработчиком им не нужно — для этого в приложение встраивается один Client ID
приложения Ali Cook. Получить его нужно один раз:

1. Зарегистрируйтесь на https://developer.home-connect.com (бесплатно).
2. «Applications» → «Register Application»:
   - Application ID: `alicook`;
   - OAuth Flow: **Device Flow**;
   - Home Connect User Account for Testing: ваш логин из приложения Home Connect;
   - остальные поля можно оставить пустыми.
3. Скопируйте **Client ID** приложения (не Client Secret).
4. На GitHub: репозиторий → Settings → Secrets and variables → Actions →
   вкладка **Variables** → New repository variable:
   - Name: `HOME_CONNECT_CLIENT_ID`
   - Value: скопированный Client ID.
5. Запустите сборку APK (workflow «Build Ali Cook APK»). Шаг
   «Insert Home Connect app ID» вставит Client ID в приложение.

Пока переменная не задана, в приложении вместо кнопки написано, что подключение
не настроено; работает только ручной ввод Client ID в разделе «Для разработчика».

## Перед публикацией для всех пользователей

Новое приложение в Home Connect сначала работает только с аккаунтами, указанными
при регистрации (для проверки). Чтобы духовки подключали все пользователи,
приложение нужно отправить на проверку Home Connect («Go Live» / партнёрская
программа) в кабинете developer.home-connect.com. Условия проверки задаёт
Home Connect — уточните их там.

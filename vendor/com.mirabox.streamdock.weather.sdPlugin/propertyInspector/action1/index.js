/**
 * 基础参数说明:
 *      @local 是否国际化
 *      @back 自主决定回显时机
 *      @dom 保存需要的文档元素
 *      @propEvent 软件回调事件 - 策略模式
 * ==================================================>
 */
const $local = true, $back = false,
    $dom = {
        main: $('.sdpi-wrapper'),
        titleWrap: $('#titleWrap'),
        tempList: $('#tempList'),
        inputCity: $('#inputCity'),
        inputTitle: $('#inputTitle'),
        themeList: $('#themeList'),
        searchBtn: $('#searchBtn'),
        searchList: $('#searchList'),
        radio: $('input[name="rdio"]', true),
        radio2: $('input[name="rdio2"]', true)

    },
    $propEvent = {
        didReceiveSettings() {
            $dom.searchList.innerHTML = ($settings.searchList || []).map(item => {
                const cityName = item.localName || item.displayName || item.name;
                // 行政区划：省/州（admin1）在前、国家（country）在后，去掉与城市名重复的层级
                const hierarchy = item.hierarchy || [];
                const division = [
                    hierarchy.find(h => h.level === 'admin1'),
                    hierarchy.find(h => h.level === 'country')
                ]
                    .map(h => h && h.name)
                    .filter((name, index, arr) => name && name !== cityName && arr.indexOf(name) === index);
                return `<option value="${item.id}">${division.length ? `${cityName}, ${division.join(', ')}` : cityName}</option>`;
            }).join('');
            $dom.tempList.value = $settings.tempList || '0';
            $dom.inputCity.value = $settings.inputCity || '';
            $dom.inputTitle.value = $settings.title || '';
            $dom.themeList.value = $settings.theme || 'Modern';
            $dom.searchList.value = $settings.cityId || '';
            titleWrap.style.display = ($settings.radio || '0') == '1' ? 'flex' : 'none';
            $dom.radio.forEach(item =>
                item.checked = item.value === ($settings.radio || '0') ? true : false);
            $dom.radio2.forEach(item =>
                item.checked = item.value === ($settings.radio2 || '0') ? true : false);
        },
        sendToPropertyInspector(data) { }
    };

// 从这里开始...
$dom.radio.forEach(item => item.on('change', function () {
    $settings.radio = this.value;
    $websocket.sendToPlugin({ radio: this.value });
    titleWrap.style.display = this.value == '1' ? 'flex' : 'none';
}));

$dom.radio2.forEach(item => item.on('change', function () {
    $settings.radio2 = this.value;
    $websocket.sendToPlugin({ radio2: this.value });
}));

// 防抖查询城市列表
const searchFunc = $.debounce(() => {
    $websocket.sendToPlugin({ inputCity: $dom.inputCity.value });
}, 1000);
$dom.inputCity.on('input', () => {
    searchFunc();
    $settings.inputCity = $dom.inputCity.value;
});

// 切换温度单位
$dom.tempList.on('change', () => {
    $settings.tempList = $dom.tempList.value;
    $websocket.sendToPlugin({ tempList: $dom.tempList.value });
});

// 搜索天气
$dom.searchList.on('change', () => {
    const cityId = $dom.searchList.value;
    if (!cityId) return;
    $settings.cityId = cityId;
    $websocket.sendToPlugin({ cityId });
});
$dom.searchBtn.on('click', () => {
    // 优先使用已保存的城市，选择框为空时也保证能触发刷新
    const cityId = $settings.cityId || $dom.searchList.value;
    if (cityId) $websocket.sendToPlugin({ cityId });
});

// 自定义标题
$dom.inputTitle.on('input', () => {
    $settings.title = $dom.inputTitle.value;
    $websocket.sendToPlugin({ title: $dom.inputTitle.value });
});

// 主题切换
$dom.themeList.on('change', () => {
    $settings.theme = $dom.themeList.value;
    $websocket.sendToPlugin({ theme: $dom.themeList.value });
});


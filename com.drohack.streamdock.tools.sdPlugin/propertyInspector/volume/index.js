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
    },
    $propEvent = {
        didReceiveSettings(data) {
            console.log("didReceiveSettings",data);
            $settings.test = 121;
            $websocket.sendToPlugin({ PropertyInspector: 121});
            $websocket.setGlobalSettings({ PropertyInspector: 165415 });
        },
        sendToPropertyInspector(data) { 
            console.log("sendToPropertyInspector",data);
        },
        didReceiveGlobalSettings(data) {
            console.log("didReceiveGlobalSettings",data);
        },
    };
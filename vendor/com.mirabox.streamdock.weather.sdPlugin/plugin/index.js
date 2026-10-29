/**
 * 基础参数说明:
 *      @plugin 全局插件行动 - 策略模式
 *      @plugin .default 行动默认数据
 *      @plugin _willAppear 在 willAppear 方法之后立即执行
 *      @plugin _willDisappear 在 willDisappear 方法之前立即执行
 *      @common sendToPlugin keyUp propertyInspectorDidAppear
 * =========================================================================>
 */
/**
 * WeatherAPI 图标编号 -> 本地图标（和风风格代码）映射。
 * 网关返回的 condition.icon 形如 //cdn.weatherapi.com/weather/64x64/day/113.png，
 * 其中的 113/116/... 是 WeatherAPI 的图标编号（与 condition.code 不是同一套数字），
 * 这里以图标编号为键映射到 static/img/Modern 下的本地图标，不再依赖网络图片。
 * 数组元素依次为: [白天图标代码, 夜间图标代码]。
 */
const WEATHER_ICON_MAP = {
  113: [100, 150], // 晴
  116: [103, 153], // 多云转晴
  119: [101, 151], // 多云
  122: [104, 154], // 阴
  143: [500, 500], // 轻雾
  176: [300, 350], // 局部阵雨
  179: [400, 407], // 局部阵雪
  182: [405, 456], // 小冻雨
  185: [309, 313], // 冻毛毛雨
  200: [302, 302], // 雷阵雨
  227: [407, 457], // 吹雪
  230: [403, 403], // 暴风雪
  248: [501, 501], // 雾
  260: [510, 510], // 冻雾
  263: [309, 309], // 小毛毛雨
  266: [309, 309], // 毛毛雨
  281: [313, 313], // 冻毛毛雨
  284: [313, 313], // 强冻毛毛雨
  293: [300, 350], // 局部小雨
  296: [305, 305], // 小雨
  299: [306, 306], // 间中有雨
  302: [306, 306], // 中雨
  305: [307, 307], // 间中有大雨
  308: [307, 307], // 大雨
  311: [313, 313], // 冻雨
  314: [313, 313], // 强冻雨
  317: [405, 456], // 小冻雨夹雪
  320: [405, 456], // 中/强冻雨夹雪
  323: [400, 407], // 局部小雪
  326: [400, 400], // 小雪
  329: [401, 408], // 局部中雪
  332: [401, 401], // 中雪
  335: [402, 409], // 局部大雪
  338: [402, 402], // 大雪
  350: [313, 313], // 冰粒
  353: [300, 350], // 小阵雨
  356: [301, 351], // 中/强阵雨
  359: [310, 310], // 强降雨
  362: [456, 456], // 小阵雨夹雪
  365: [456, 456], // 中/强阵雨夹雪
  368: [407, 457], // 小阵雪
  371: [408, 457], // 中/强阵雪
  374: [456, 456], // 小冰粒阵
  377: [456, 456], // 中/强冰粒阵
  386: [302, 302], // 雷阵雨
  389: [303, 303], // 强雷阵雨
  392: [407, 457], // 雷阵雪
  395: [401, 401], // 强雷阵雪
};

/**
 * WeatherAPI condition.code -> 图标编号（1000~1282 -> 113~395，一一对应）。
 * 仅当网关没有返回 icon 时兜底使用。
 */
const CONDITION_TO_ICON = {
  1000: 113, 1003: 116, 1006: 119, 1009: 122, 1030: 143,
  1063: 176, 1066: 179, 1069: 182, 1072: 185, 1087: 200,
  1114: 227, 1117: 230, 1135: 248, 1147: 260, 1150: 263,
  1153: 266, 1168: 281, 1171: 284, 1180: 293, 1183: 296,
  1186: 299, 1189: 302, 1192: 305, 1195: 308, 1198: 311,
  1201: 314, 1204: 317, 1207: 320, 1210: 323, 1213: 326,
  1216: 329, 1219: 332, 1222: 335, 1225: 338, 1237: 350,
  1240: 353, 1243: 356, 1246: 359, 1249: 362, 1252: 365,
  1255: 368, 1258: 371, 1261: 374, 1264: 377, 1273: 386,
  1276: 389, 1279: 392, 1282: 395,
};

/** 本地已有的图标代码（和风风格，static/img/Modern） */
const LOCAL_WEATHER_CODES = new Set([
  100, 101, 102, 103, 104, 150, 151, 152, 153, 154,
  300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318,
  350, 351, 399,
  400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410,
  456, 457, 499,
  500, 501, 502, 503, 504, 507, 508, 509, 510, 511, 512, 513, 514, 515,
  900, 901, 999,
]);

/**
 * 根据天气图标信息返回本地图标路径。
 * @param {number|string} code - 天气代码（condition.code）
 * @param {number} [isDay] - 是否白天（1 白天 / 0 夜晚）
 * @param {string} [iconUrl] - 网关返回的天气图标地址（形如 //cdn.weatherapi.com/weather/64x64/day/113.png）
 * @param {string} [theme] - 图标主题（Modern 简约摩登 / Luxury 豪华绚丽）
 * @returns {string} 本地图标相对路径
 */
function getWeatherIconPath(code, isDay, iconUrl, theme) {
  const localCode = getLocalWeatherCode(code, isDay, iconUrl);
  if (!localCode) return "../static/img/default.jpg";

  // 按主题选择本地图标：Luxury 豪华绚丽 / 默认 Modern 简约摩登
  if (theme === "Luxury") {
    return `../static/img/Luxury/${LuxuryEnum[localCode] || '100'}.png`;
  }
  return `../static/img/Modern/${localCode}-fill.svg`;
}

/**
 * 解析出本地（和风风格）天气代码，用于本地图标和国际化天气名称。
 * @param {number|string} code - 天气代码（condition.code）
 * @param {number} [isDay] - 是否白天（1 白天 / 0 夜晚）
 * @param {string} [iconUrl] - 网关返回的天气图标地址
 * @returns {number|null} 本地天气代码（如 100/101/104…），无法识别时返回 null
 */
function getLocalWeatherCode(code, isDay, iconUrl) {
  // 优先从 icon URL 中提取 WeatherAPI 图标编号（如 113）
  const match = /(?:day|night)\/(\d+)\.(?:png|svg)/i.exec(iconUrl || '');
  let iconCode = match ? Number(match[1]) : null;
  // 提取不到时用 condition.code 兜底转换（1000~1282 -> 113~395）
  if (!iconCode) iconCode = CONDITION_TO_ICON[Number(code)] || null;

  const icons = WEATHER_ICON_MAP[iconCode];
  if (icons) return isDay ? icons[0] : icons[1];
  // 兜底：本身就是本地图标代码（和风风格）时直接使用
  const c = Number(code);
  if (LOCAL_WEATHER_CODES.has(c)) return c;
  return null;
}

/**
 * Draws the weather name and temperature into the image below the icon, for the
 * "None" display option. setTitle cannot change the font size, so this is the
 * only way to let the temperature grow into the line the city name would use.
 * Font family and color follow the key's title settings. The text is always
 * bold because StreamDock draws key titles bold even when the style is Regular.
 */
function drawReading(ctx, weatherName, tempText, titleParameters) {
  const tp = titleParameters || {};
  const style = (tp.fontStyle || "").toLowerCase();
  const font = (px) =>
    `${style.includes("italic") ? "italic " : ""}bold ${px}px "${tp.fontFamily || "Microsoft YaHei"}", sans-serif`;
  // Largest font whose ink fits the 480px-wide box between top and bottom,
  // centered vertically for when the width is the limit.
  const fit = (text, top, bottom) => {
    ctx.font = font(100);
    const m = ctx.measureText(text);
    const inkHeight = m.actualBoundingBoxAscent + m.actualBoundingBoxDescent;
    ctx.font = font(Math.floor(100 * Math.min(480 / m.width, (bottom - top) / inkHeight)));
    const s = ctx.measureText(text);
    ctx.fillText(text, 256, (top + bottom + s.actualBoundingBoxAscent - s.actualBoundingBoxDescent) / 2);
  };

  ctx.save();
  ctx.fillStyle = tp.titleColor || "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  // Localized names can hold "\n" (e.g. "Clear\nat night"); one line reads better here.
  const nameLine = (weatherName || "").replace(/\n/g, " ");
  if (nameLine) {
    fit(nameLine, 292, 348);
    fit(tempText, 364, 496);
  } else {
    fit(tempText, 300, 496);
  }
  ctx.restore();
}

const $local = false,
  $plugin = {
    name: "weather",
    action1: new Action({
      default: {
        inputCity: "", // 输入框
        tempList: "0", // 
        cityId: "",
        city: "",
        title: "",
        radio: "0",
        radio2: "0",
        searchList: [],
        theme: "Modern",
        wdata: { tmp: "20", code: "101", name: '', cityName: '', isDay: 1, icon: '' },
        titleParameters: {
          titleColor: "#ffffff",
        },
        count: 0
      },
      async queryLocation(context, device) {
        console.log("queryLocation");
        const data = this.data[context];
        const langMap = {
          'zh_CN': 'zh', 'en': 'en', 'ja': 'ja', 'fr': 'fr',
          'it': 'it', 'ru': 'ru', 'es': 'es', 'pt': 'pt', 'de': 'de'
        };
        const lang = langMap[$lang] || 'en';
        const weatherService = window.WeatherServiceFactory.createWeatherService(); // 获取天气服务实例
      
        try {
          if (data.inputCity) {
            // console.log("inputCity");
            $websocket.setTitle(context, "Loading");
            const [error, locationList] = await weatherService.queryLocation(data.inputCity, lang);
      
            if (error) {
              console.error("queryLocation failed:", error);
              data.searchList = [];
              this.canvasFunc(context, device, "error");
              $websocket.setSettings(context, data);
              this.scheduleRetry(context, device, "queryLocation");
            } else if (locationList && locationList.length > 0) {
              // 网关返回的是包含城市信息的数组，每一项已归一化为 { id: geonameId, name: 本地化名称 }
              data.searchList = locationList;
              this.queryWeather(context, device);
              data.count = 0;
            } else {
              data.searchList = [];
              this.canvasFunc(context, device, "404");
              $websocket.setSettings(context, data);
            }
          }
        } catch (e) {
          console.error("queryLocation general error:", e);
          if (++data.count <= 3) {
            this.queryLocation(context, device);
            $websocket.setTitle(context, "Try again");
            return;
          }
          this.canvasFunc(context, device, "error");
          this.scheduleRetry(context, device, "queryLocation");
        }
      },
      async queryWeather(context, device) {
        const data = this.data[context];
        const weatherService = window.WeatherServiceFactory.createWeatherService(); // 获取天气服务实例
        const langMap = {
          'zh_CN': 'zh', 'en': 'en', 'ja': 'ja', 'fr': 'fr',
          'it': 'it', 'ru': 'ru', 'es': 'es', 'pt': 'pt', 'de': 'de'
        };
        const lang = langMap[$lang] || 'en';
        try {
          clearTimeout(data.timer);
          console.log(data, data.cityId, data.searchList);
          // 过滤出用户选择的城市（searchList 为空时保留已有 cityId，
          // 避免搜索失败/重启后按键或属性检查器更新变成无效操作）
          if (data.searchList && data.searchList.length) {
            const selected =
              data.searchList.find((item) => item.id === data.cityId) || data.searchList[0];
            if (selected) {
              data.cityId = selected.id;
              // 城市名称用搜索结果里选中的本地名称（localName），
              // 而不是 current 接口返回的气象站名称（如 徐家汇）
              data.city = selected.localName || selected.displayName || selected.name || data.city;
            }
          }
          if (!data.cityId) return; // 未选择城市，不发起请求

          $websocket.setTitle(context, "Loading");
          const [error, weatherData] = await weatherService.queryWeather(data.cityId, lang);

          if (error) {
            console.error("queryWeather failed:", error);
            this.canvasFunc(context, device, "error");
            this.scheduleRetry(context, device, "queryWeather");
          } else if (weatherData && weatherData.data && weatherData.data.current) {
            // 网关返回 { data: { location, current }, meta: {...} }
            const current = weatherData.data.current;
            const tmp = current.tempC;
            const code = current.condition && current.condition.code;
            const name = (current.condition && current.condition.text) || '';
            const cityName = data.city || data.wdata.cityName || '';
            const icon = (current.condition && current.condition.icon) || '';

            data.wdata = { tmp, code, name, cityName, isDay: current.isDay, icon };
            data.count = 0;
            data.timer = setTimeout(
              () => this.queryWeather(context, device),
              1000 * 60 * 10
            );
            $websocket.setSettings(context, data);
            this.canvasFunc(context, device);
          } else {
            this.canvasFunc(context, device, "error");
            this.scheduleRetry(context, device, "queryWeather");
          }
        } catch (e) {
          console.error("queryWeather general error:", e);
          if (++data.count <= 3) {
            this.queryWeather(context, device);
            $websocket.setTitle(context, "Try again");
            return;
          }
          this.canvasFunc(context, device, "error");
          this.scheduleRetry(context, device, "queryWeather");
        }
      },
      // The refresh timer is only re-armed on success, so without this one
      // failed fetch would stop the key updating until it is pressed.
      scheduleRetry(context, device, method, delay = 1000 * 60 * 5) {
        const data = this.data[context];
        clearTimeout(data.timer);
        data.timer = setTimeout(() => {
          data.count = 0;
          this[method](context, device);
        }, delay);
      },
      // 绘制
      async canvasFunc(context, device, status = "success") {
        if (status === "error") {
          $websocket.setImage(
            context,
            this.data[context].isBackgroundHidden
              ? "../static/img/tm.png"
              : "../static/img/default.jpg"
          );
          $websocket.setTitle(context, "Timeout");
          return;
        } else if (status === "404") {
          $websocket.setImage(
            context,
            this.data[context].isBackgroundHidden
              ? "../static/img/tm.png"
              : "../static/img/default.jpg"
          );
          $websocket.setTitle(context, "Not found");
          return;
        }
        if (!this.data[context].cityId) return;

        // 主题配置
        const data = this.data[context];
        const { tmp, code, name, cityName, icon } = data.wdata;
        // 摄氏度/华氏度
        const unit = data.tempList === "0" ? "℃" : "℉";
        const tmps = data.tempList === "0" ? tmp : tmp * 1.8 + 32;

        // 根据 icon URL 中的图标编号映射本地图标，不依赖网关返回的网络图片
        const iconSrc = getWeatherIconPath(code, data.wdata.isDay, icon, data.theme);
        // 天气名称：优先按天气代码从国际化 json 中取（154 与 153 同为夜间多云），接口文本仅兜底
        const localCode = getLocalWeatherCode(code, data.wdata.isDay, icon);
        const localizedName =
          data.Localization && data.Localization[localCode == 154 ? 153 : localCode];

        const render = (icon) => {
          let canvas = document.createElement("canvas");
          canvas.width = canvas.height = 512;
          let ctx = canvas.getContext("2d");

          ctx.fillStyle = "rgba(0,0,0,0)";
          ctx.fillRect(0, 0, 512, 512);
          ctx.save();

          if (data.theme === "Luxury") {
            // 豪华绚丽：512x512 满幅 PNG，铺满整个键位（微扩 2px 避免边缘白边）
            ctx.drawImage(icon, -2, -2, 516, 516);
          } else {
            // 简约摩登：SVG 按原始比例等比缩放后居中绘制（兼容无显式宽高的 SVG）
            const size = 260;
            const naturalW = icon.naturalWidth || size;
            const naturalH = icon.naturalHeight || size;
            const scale = Math.min(size / naturalW, size / naturalH);
            const drawW = naturalW * scale;
            const drawH = naturalH * scale;
            ctx.drawImage(icon, (512 - drawW) / 2, 20 + (size - drawH) / 2, drawW, drawH);
          }

          if (data.radio == "2") {
            drawReading(ctx, data.radio2 == "0" ? localizedName || name : "", `${Number(tmps).toFixed(1)}${unit}`, data.titleParameters);
            $websocket.setTitle(context, "");
          } else {
            const weatherName = data.radio2 == "0" ? (localizedName || name) + "\n" : '';
            $websocket.setTitle(
              context,
              weatherName + (data.radio == "0" ? `${Number(tmps).toFixed(1)}${unit}\n${cityName}` : `${Number(tmps).toFixed(1)}${unit}\n${data.title}`)
            );
          }

          $websocket.setImage(context, canvas.toDataURL("image/png"));
        };

        const image = new Image();
        image.src = iconSrc;
        image.onload = function () {
          render(this);
        };
        image.onerror = function () {
          // 本地图标缺失时兜底显示默认背景
          const fallback = new Image();
          fallback.src = "../static/img/default.jpg";
          fallback.onload = function () {
            render(this);
          };
        };
      },
      titleParametersDidChange({ context, payload, device }) {
        this.data[context].titleParameters = payload.titleParameters;
        this.canvasFunc(context, device);
      },
      didReceiveSettings({ context, payload, device }) {
        this.data[context].isBackgroundHidden = payload.settings.isBackgroundHidden;
        this.canvasFunc(context, device);
      },
      async _willAppear({ context, device, payload }) {
        console.log("willAppear", payload);
        // 加载国际化 json，天气名称按天气代码从 Localization 中取
        this.data[context].Localization = await new Promise((resolve) => {
          const req = new XMLHttpRequest();
          req.open('GET', `../${$lang}.json`);
          req.send();
          req.onreadystatechange = () => {
            if (req.readyState === 4) {
              try {
                resolve(JSON.parse(req.responseText).Localization || {});
              } catch (e) {
                console.error("加载国际化文件失败:", e);
                resolve({});
              }
            }
          };
        });
        this.queryLocation(context, device);
      },
      _willDisappear({ context}) {
        clearTimeout(this.data[context].timer);
      },
      sendToPlugin({ context, payload, device }) {
        const data = this.data[context];
        const { inputCity, cityId, title, theme, radio, radio2, tempList } = payload;

        // 输入城市
        if (inputCity !== undefined) {
          data.inputCity = inputCity;
          this.data[context].count = 0;
          return this.queryLocation(context, device);
        }
        // 更新天气
        if (cityId !== undefined && cityId !== '') {
          data.cityId = cityId;
          this.data[context].count = 0;
          return this.queryWeather(context, device);
        }
        // 更新选项
        if (title !== undefined) data.title = title;
        if (theme !== undefined) data.theme = theme;
        if (radio !== undefined) data.radio = radio;
        if (radio2 !== undefined) data.radio2 = radio2;
        if (tempList !== undefined) data.tempList = tempList;
        this.canvasFunc(context, device);
      },
      keyUp({ context, device }) {
        this.data[context].count = 0;
        this.queryWeather(context, device);
      },
    }),
  };

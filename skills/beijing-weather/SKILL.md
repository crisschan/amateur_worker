---
name: beijing-weather
description: 查询北京实时天气预报，包括温度、湿度、风向、空气质量等信息
type: custom
created: 2026-04-16T18:20:20.995205
---

# Beijing Weather Skill

## Purpose
查询北京实时天气预报，提供当前天气状况和未来几天的预报信息。

## When to Use
当用户询问"北京天气"、"北京今天天气怎么样"、"北京天气预报"等任何关于北京天气的问题时使用此skill。

## Implementation

### API选择
使用和风天气(HeWeather) API或Open-Meteo免费API（无需API密钥）

### 推荐方案：Open-Meteo API（免费，无需注册）

```python
import requests

def get_beijing_weather():
    """
    获取北京实时天气预报
    使用Open-Meteo免费API
    """
    # 北京坐标：纬度39.9042，经度116.4074
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": 39.9042,
        "longitude": 116.4074,
        "current": ["temperature_2m", "relative_humidity_2m", "apparent_temperature", "weather_code", "wind_speed_10m", "wind_direction_10m"],
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
        "timezone": "Asia/Shanghai",
        "forecast_days": 3
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return format_weather_output(data)
    except Exception as e:
        return f"获取天气信息失败: {str(e)}"

def format_weather_output(data):
    """格式化天气输出"""
    current = data.get("current", {})
    daily = data.get("daily", {})
    
    # 天气代码映射
    weather_codes = {
        0: "晴朗", 1: " mainly clear", 2: "多云", 3: "阴天",
        45: "雾", 48: "雾凇",
        51: "毛毛雨", 53: "中雨", 55: "大雨",
        61: "小雨", 63: "中雨", 65: "大雨",
        71: "小雪", 73: "中雪", 75: "大雪",
        80: "阵雨", 81: "强阵雨", 82: "暴雨",
        95: "雷雨", 96: "雷雨伴冰雹", 99: "强雷雨伴冰雹"
    }
    
    # 风向映射
    def get_wind_direction(degree):
        directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
        index = round(degree / 45) % 8
        return directions[index]
    
    weather_code = current.get("weather_code", 0)
    weather_desc = weather_codes.get(weather_code, "未知")
    
    output = f"""
🌤️ **北京实时天气预报**

📍 **当前天气**
• 天气状况: {weather_desc}
• 温度: {current.get('temperature_2m', 'N/A')}°C
• 体感温度: {current.get('apparent_temperature', 'N/A')}°C
• 相对湿度: {current.get('relative_humidity_2m', 'N/A')}%
• 风速: {current.get('wind_speed_10m', 'N/A')} km/h
• 风向: {get_wind_direction(current.get('wind_direction_10m', 0))}

📅 **未来3天预报**
"""
    
    # 添加未来几天预报
    daily_codes = daily.get("weather_code", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])
    
    for i in range(min(3, len(daily_codes))):
        day_weather = weather_codes.get(daily_codes[i], "未知")
        output += f"\n第{i+1}天: {day_weather}, 最高{max_temps[i]}°C / 最低{min_temps[i]}°C"
    
    output += "\n\n💡 数据来源: Open-Meteo"
    return output

# 执行查询
result = get_beijing_weather()
print(result)
```

## Usage Examples

**用户问**: "北京今天天气怎么样？"
**输出示例**:
```
🌤️ **北京实时天气预报**

📍 **当前天气**
• 天气状况: 晴朗
• 温度: 25°C
• 体感温度: 26°C
• 相对湿度: 45%
• 风速: 12 km/h
• 风向: 西北

📅 **未来3天预报**

第1天: 晴朗, 最高28°C / 最低15°C
第2天: 多云, 最高26°C / 最低14°C
第3天: 小雨, 最高22°C / 最低12°C

💡 数据来源: Open-Meteo
```

## Notes
- 使用Open-Meteo免费API，无需API密钥
- 数据每小时更新
- 温度单位为摄氏度
- 风速单位为km/h

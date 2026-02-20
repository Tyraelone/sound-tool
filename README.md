# sound-tool

Win11 下的“声音方位罗盘浮窗”示例程序。

## 你要的能力
- 采集系统正在播放的立体声（WASAPI loopback，非内存注入）。
- 通过左右声道能量差估算声音来源方向。
- 浮窗罗盘实时显示方位角（-90° 左侧，+90° 右侧）。

## 关键限制（必须说明）
- 仅靠双声道输出，通常只能稳定判断“左/右偏向”。
- 前后同角度在很多场景会混淆，无法仅凭立体声精确反推敌方真实世界坐标。
- 如果游戏用了虚拟环绕/HRTF，结果会比纯双声道更复杂，需重新标定。

## 环境
- Windows 11
- Python 3.10+

## 安装
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 运行
```powershell
python sound_locator.py
```

## 退出
- 按 `Esc` 关闭。

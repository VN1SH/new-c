# new-c - Windows C盘清理工具 + AI 深度建议）

## 项目简介
new-c 是一个面向 Windows 10/11 的 C 盘清理工具，提供规则扫描、占比分析、AI 深度建议与 AI 盘点报告。工具默认使用安全策略（优先回收站、硬禁系统目录），并提供清理计划与结果记录，适合谨慎清理与专业审计场景。

## 功能亮点
- 类 CCleaner 常见清理项（临时文件、缓存、日志等）
- AI 深度建议（五级清理建议）+ AI 盘点报告
- C盘占比分析（扩展名/目录/类别/Top 大文件）
- 多页面 UI：Dashboard / Cleaner / Analyzer / AI Advisor / AI Report / Settings
- 清理策略：优先回收站，失败再提示永久删除

## 风险提示
- 清理工具具有数据删除风险，请在充分理解清理项的前提下使用。
- 默认不清理系统关键路径（System32、WinSxS、Program Files 等）。
- AI 建议仅基于文件元数据与统计信息推断，不读取文件内容，无法替代人工判断。

## 隐私说明
- 默认启用路径脱敏，仅上传路径尾部片段+哈希，不上传文件内容。
- 可在 Settings 中选择是否上传完整路径。
- 仅上传结构化扫描数据，不上传实际文件内容。

## 离线模式
- 未配置 API Key 时，AI 分析不可用，仍可使用本地扫描与清理。

## 运行方式（PowerShell 一键）
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 打包为 EXE（PyInstaller）
```powershell
.\.venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm --windowed --name new-c main.py
```

## FAQ
**Q: 清理后是否可恢复？**  
A: 默认使用回收站，可从回收站恢复；永久删除需要确认。  

**Q: AI 建议可靠吗？**  
A: AI 建议基于元数据推断，建议作为辅助参考，并结合风险提示判断。  

**Q: 为什么某些目录无法扫描？**  
A: 可能因为权限不足或目录被占用，相关错误会记录在 scan_cache.json 中。  

## 数据文件说明
运行后会在 `data/runtime` 生成以下文件：
- scan_cache.json
- analysis_stats.json
- analysis_payload.json
- ai_advice.json
- ai_report.json
- cleanup_plan.json
- cleanup_result.json

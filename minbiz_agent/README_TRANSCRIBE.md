# Henry 视频录屏转文本（Fulltext）与合规检索分流

本项目将“**完整转录存档**”与“**合规检索索引**”明确分离：

- **Fulltext 存档（私人备份）**：
  - 脚本：`python -m src.ingest.transcribe_fulltext`
  - 输出：`data/fulltext/*.jsonl` 与 `data/fulltext/*.txt`
  - 用途：仅供你个人内部查看或在未来其它系统中**引用摘要**。**不要对外分发，不要直接纳入索引或训练。**

- **合规检索索引（供Agent检索回答）**：
  - 脚本：`python -m src.ingest.pipeline`（会执行PII脱敏+分块）
  - 输出：`data/chunks/*.chunks.jsonl`（标记了 `flags=["pii_redacted"]`）
  - 后续：`python -m src.index.build_index` -> `streamlit run streamlit_app.py`

- **Google Drive 导出**（如果需要自动化从云端下载视频到本地）：
  - 脚本：`python -m src.ingest.gdrive_export --folder_path "创业/Henry视频录屏"`
  - 需要 `credentials.json`（OAuth 客户端），首次运行会弹出浏览器授权。

## 推荐流程
1. `python -m src.ingest.gdrive_export --folder_path "创业/Henry视频录屏"`  （可选）  
2. `python -m src.ingest.transcribe_fulltext`  —— 生成**完整转录**（私人存档）  
3. `python -m src.ingest.pipeline`  —— 生成**脱敏分块**（用于索引/训练）  
4. `python -m src.index.build_index`  
5. `streamlit run streamlit_app.py`

> ⚠️ 合规提醒：**Fulltext** 文件请仅私人保存，不要对外共享及商用分发；训练/检索统一使用 `pipeline` 产物，以保护隐私与知识产权。


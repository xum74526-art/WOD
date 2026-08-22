# KAI Collector

独立外部数据采集服务。它不导入 FastAPI 的 ORM，不连接业务数据库，只把标准化批次提交到 FastAPI 内部 ingestion 接口。

## 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

为 Collector 和 FastAPI 配置相同的独立 ingestion token，并在确认来源授权后设置：

```dotenv
VAST_COLLECTION_AUTHORIZED=true
```

单次同步和常驻调度：

```powershell
python -m collector sync all
python -m collector run
```

Vast.ai 搜索结果按 `incremental` 批次提交，因为搜索响应不是经过证明的完整市场快照。Collector 不保存公网 IP、主机名或上游响应正文。

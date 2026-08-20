"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import { FileLock, FolderOpen, UploadSimple } from "@phosphor-icons/react";
import { getPrivateFiles, uploadPrivateFile, type PrivateFilesSnapshot } from "@/lib/integration-api";
import { ProviderState } from "@/components/provider-state";

function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function PrivateFilesWorkspace() {
  const [data, setData] = useState<PrivateFilesSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  function load() { getPrivateFiles().then(setData).catch((reason) => setError(reason instanceof Error ? reason.message : "私有文件服务暂时不可用")); }
  useEffect(load, []);

  async function selected(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !data) return;
    if (file.size > data.max_upload_bytes) {
      setError(`文件不能超过 ${fileSize(data.max_upload_bytes)}`);
      event.target.value = "";
      return;
    }
    setBusy(true);
    setError("");
    try {
      await uploadPrivateFile(file, "general_private");
      load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  if (!data) return <section className="workspace-page"><div className="workspace-skeleton" aria-label="正在读取私有文件" />{error && <div className="commerce-error">{error}</div>}</section>;
  return (
    <section className="workspace-page integration-workspace">
      <div className="workspace-page__head integration-head"><div><p>ACCOUNT / PRIVATE FILES</p><h1>私有文件</h1><span>文件通过短期签名地址直传，数据库只保存权限受控的元数据。</span></div><button disabled={!data.provider.configured || busy} onClick={() => input.current?.click()}><UploadSimple size={16} />{busy ? "上传中…" : "上传文件"}</button><input ref={input} hidden type="file" onChange={(event) => void selected(event)} /></div>
      <ProviderState descriptor={data.provider} />
      <div className="integration-safety-note"><FileLock size={21} /><div><strong>仅限私有对象</strong><span>最大 {fileSize(data.max_upload_bytes)}。真实供应商接入前不会接受任何文件内容。</span></div></div>
      <section className="private-file-ledger">
        <header><span>文件</span><span>分类</span><span>大小</span><span>状态</span></header>
        {data.objects.length ? data.objects.map((file) => <article key={file.id}><span><small>{file.object_no}</small><strong>{file.filename}</strong></span><span>{file.category}</span><span>{fileSize(file.size_bytes)}</span><b>{file.status}</b></article>) : <div className="commerce-empty"><FolderOpen size={25} /><strong>暂无私有文件</strong><span>{data.provider.configured ? "可以上传第一份私有文件。" : "对象存储接入后开放上传。"}</span></div>}
      </section>
      {error && <div className="commerce-error">{error}</div>}
    </section>
  );
}

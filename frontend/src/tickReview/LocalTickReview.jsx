import {useEffect,useRef,useState} from 'react';
import {explanations,intervalText,nanoseconds,ReviewLoader,utcTime} from './ReviewImport.js';
import './LocalTickReview.css';

export default function LocalTickReview(){
  const [loader]=useState(()=>new ReviewLoader());
  const [files,setFiles]=useState({artifact:null,report:null});
  const [review,setReview]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const [page,setPage]=useState(0),[inputKey,setInputKey]=useState(0);
  const generation=useRef(0);
  useEffect(()=>()=>{generation.current++;loader.cancel();},[loader]);
  const clear=()=>{generation.current++;loader.cancel();setReview(null);setError('');setLoading(false);setPage(0);};
  const choose=(kind,file)=>{clear();setFiles(current=>({...current,[kind]:file??null}));};
  const reset=()=>{clear();setFiles({artifact:null,report:null});setInputKey(key=>key+1);};
  const load=async()=>{
    clear();const request=generation.current;setLoading(true);
    try{
      const result=await loader.load(files.artifact,files.report);
      if(request===generation.current)setReview(result);
    }catch(problem){if(request===generation.current&&problem.name!=='AbortError')setError(problem.message);}
    finally{if(request===generation.current)setLoading(false);}
  };
  const artifact=review?.artifact,report=review?.report;
  const rows=artifact?.quotes??[],pageCount=Math.max(1,Math.ceil(rows.length/50));
  const reasons=report?[...new Set([...report.issues,report.quoteDecision.reason])]:[];
  return <main className="tick-review">
    <header><div><p className="tick-review-eyebrow">BACKTEST LAB · PERSONAL LOCAL REVIEW</p><h1>Local Tick Review</h1></div><a href="/">Kembali ke workspace</a></header>
    <p>Review bukti quote secara read-only. Tidak ada order, perubahan saldo, fill atau PnL.</p>
    <section aria-labelledby="review-import-heading">
      <h2 id="review-import-heading">Pilih dua file lokal</h2>
      <p>Artifact tick dan laporan evaluator Python. Maksimal 1 MiB per file dan 1.024 quote. File tetap di memori tab ini; tidak diunggah atau disimpan ke akun.</p>
      <details><summary>Cara menyiapkan laporan lokal</summary><p>Siapkan laporan memakai <code>python -m precision.policy --artifact FILE --sha256 HASH</code> dari folder backend, lalu simpan stdout secara lokal sebagai JSON UTF-8. Jangan unggah data personal ke GitHub.</p></details>
      <div className="tick-review-import" key={inputKey}>
        <label>Artifact tick<input type="file" accept=".json,application/json" onChange={event=>choose('artifact',event.target.files?.[0])}/></label>
        <label>Laporan evaluator<input type="file" accept=".json,application/json" onChange={event=>choose('report',event.target.files?.[0])}/></label>
      </div>
      <div className="tick-review-actions"><button onClick={load} disabled={!files.artifact||!files.report||loading}>Periksa file</button><button onClick={reset}>Reset review</button></div>
      <p role="status" aria-live="polite">{loading?'Memeriksa struktur dan kecocokan hash…':review?'Konsistensi kedua file cocok.':!error?'Belum ada hasil review.':''}</p>
      {error&&<p role="alert">File ditolak: <code>{error}</code>. Tidak ada hasil parsial. Periksa format, versi dan pasangan file.</p>}
    </section>
    {review&&<>
      <section aria-labelledby="review-result-heading">
        <h2 id="review-result-heading">Hasil laporan lokal</h2><p className="tick-review-status">{report.status}</p>
        <p>{artifact.instrumentId} · {artifact.feedId} · {artifact.datasetId} / {artifact.datasetVersion}</p>
        {(artifact.datasetId.startsWith('synthetic')||artifact.feedId==='authored')&&<p>Metadata artifact menandai data synthetic / authored. Contoh ini bukan histori pasar nyata.</p>}
        <p className="tick-review-warning">Hash cocok hanya membuktikan konsistensi file, bukan keaslian provider, bukti evaluator benar-benar dijalankan, atau eksekusi broker. Deklarasi reviewed evidence tetap membutuhkan review sumber terpisah.</p>
        <details><summary>Identitas dataset, skenario dan hash</summary><dl className="tick-review-meta">
          <dt>Dataset / versi</dt><dd>{artifact.datasetId} / {artifact.datasetVersion}</dd>
          <dt>Instrument / feed</dt><dd>{artifact.instrumentId} / {artifact.feedId}</dd>
          <dt>Profile / sisi</dt><dd>{artifact.profileVersion} / {artifact.side}</dd>
          <dt>Aktivasi / horizon UTC</dt><dd>{utcTime(artifact.activationNs)} → {utcTime(artifact.horizonNs)}</dd>
          <dt>Batas coverage yang dideklarasikan</dt><dd>{utcTime(artifact.coverageStartNs)} → {utcTime(artifact.coverageEndNs)}</dd>
          <dt>SL / TP skenario</dt><dd>{artifact.sl} / {artifact.tp} · parameter artifact, bukan transaksi nyata</dd>
          <dt>Coverage / sequence artifact</dt><dd>{artifact.coverageComplete?'Dideklarasikan lengkap':'Belum terbukti'} / {artifact.trustedSequence?'Dideklarasikan trusted':'Belum terbukti'}</dd>
          <dt>Execution</dt><dd>{report.executionStatus} · fill tidak tersedia · PnL tidak tersedia</dd>
          <dt>Versi policy / evaluator</dt><dd>{report.artifact} / {report.quoteDecision.evaluator_version}</dd>
          <dt>Input hash</dt><dd><code>{report.inputHash}</code></dd>
          <dt>Policy hash</dt><dd><code>{report.policyHash}</code></dd>
          <dt>Dataset hash deklarasi</dt><dd><code>{artifact.datasetHash}</code> · identitas deklarasi; bukan verifikasi arsip provider</dd>
          <dt>Effective evidence hash</dt><dd><code>{report.quoteDecision.evidence_hash}</code> · input setelah pembatasan flags oleh policy</dd>
          <dt>Referensi coverage / freshness / sequence</dt><dd>{report.declaredEvidence?.coverage_ref??'Unknown'} / {report.declaredEvidence?.freshness_ref??'Unknown'} / {report.declaredEvidence?.sequence_ref??'Unknown'}</dd>
          <dt>Long-silence diagnostic</dt><dd>{report.observedSilences} · threshold {intervalText(report.silenceWarningNs)} · interval maksimum {intervalText(report.maxIntervalNs)}</dd>
        </dl></details>
        <h3>Alasan dan batas bukti</h3>
        <ul>{reasons.map(reason=><li key={reason}><code>{reason}</code> — {explanations[reason]}</li>)}</ul>
        <p>Diagnostik mencakup supplied revealed interval. Jeda panjang belum membuktikan sesi tutup atau data hilang. Masalah setelah crossing tidak otomatis mengubah urutan crossing sebelumnya.</p>
        {report.quoteDecision.event_id&&<p>Event crossing yang dilaporkan: <strong>{report.quoteDecision.event_id}</strong> · harga quote <strong>{report.quoteDecision.observed_price}</strong>, bukan harga fill.</p>}
        <p>Aturan simulasi gap memakai harga pertama yang tersedia tetap terpisah dari laporan bukti ini. Review tidak menerapkan aturan itu ke saldo.</p>
      </section>
      <section aria-labelledby="review-quotes-heading">
        <h2 id="review-quotes-heading">Quote sesuai urutan artifact</h2>
        <p>{rows.length} quote pada window yang diberikan; bukan seluruh bulan atau sepuluh tahun. Sebelum aktivasi ditandai. Timestamp dan harga ditampilkan tanpa pembulatan.</p>
        <div className="tick-review-table" tabIndex="0" role="region" aria-label="Tabel quote, geser horizontal bila diperlukan">
          <table><caption>Bid/ask lokal · maksimal 50 baris per halaman</caption><thead><tr>{['Event','Waktu UTC','Bid','Ask','Sequence sumber','Freshness deklarasi','Gap deklarasi','Interval sebelumnya','Catatan'].map(label=><th key={label} scope="col">{label}</th>)}</tr></thead>
            <tbody>{rows.slice(page*50,(page+1)*50).map((quote,i)=>{
              const index=page*50+i,delta=index?nanoseconds(quote.timeNs)-nanoseconds(rows[index-1].timeNs):null;
              const long=delta!==null&&delta>nanoseconds(report.silenceWarningNs);
              return <tr key={index} className={quote.id===report.quoteDecision.event_id?'tick-review-crossing':''}>
                <td>{quote.id}</td><td>{utcTime(quote.timeNs)}</td><td>{quote.bid??'Unknown'}</td><td>{quote.ask??'Unknown'}</td><td>{quote.sequence??'Unknown'}</td>
                <td>{quote.fresh?'Dideklarasikan fresh':'Unknown / tidak memenuhi flag'}</td><td>{quote.gapBefore?'Gap dideklarasikan':'Tidak dideklarasikan'}</td><td>{delta===null?'—':intervalText(delta)}</td>
                <td>{nanoseconds(quote.timeNs)<nanoseconds(artifact.activationNs)?'Sebelum aktivasi · ':''}{long?'Long silence · ':''}{delta!==null&&delta<0n?'Waktu mundur · ':''}{quote.id===report.quoteDecision.event_id?'Crossing dilaporkan':''}</td>
              </tr>;
            })}</tbody>
          </table>{rows.length===0&&<p>Tidak ada quote pada artifact ini.</p>}
        </div>
        <nav className="tick-review-actions" aria-label="Halaman quote"><button disabled={page===0} onClick={()=>setPage(n=>n-1)}>Halaman sebelumnya</button><span aria-live="polite">Halaman {page+1} / {pageCount}</span><button disabled={page+1>=pageCount} onClick={()=>setPage(n=>n+1)}>Halaman berikutnya</button></nav>
      </section>
    </>}
  </main>;
}

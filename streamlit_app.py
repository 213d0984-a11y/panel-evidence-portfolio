"""Local, source-first portfolio UI. Uploaded PDF text is never HTML."""
from pathlib import Path
import json
import streamlit as st
from panel_rag.bootstrap import build_service
from panel_rag.evaluation import evaluate, load_dataset, summarize

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title="Panel Evidence | 技術文書検索",page_icon="⚡",layout="wide")
st.markdown("""
<style>
.stApp {background:#f5f7fa}
h1 {letter-spacing:-.04em;color:#163047}
div[data-testid="stMetric"] {background:white;border:1px solid #dde4eb;border-radius:12px;padding:15px}
</style>
""",unsafe_allow_html=True)

@st.cache_resource(show_spinner=False)
def get_service():
    return build_service(ROOT)

st.caption("PANEL EVIDENCE  /  技術者のための文書検索")
st.title("技術仕様を、根拠から確認する。")
st.write("複数の資料から、型式・仕様・出典を確認。十分な根拠が見つからなければ回答を控えます。")
try:
    with st.spinner("検索モデルを準備しています。初回のみダウンロードが必要です。"):
        service,settings=get_service()
except Exception as exc:
    st.error(f"起動できませんでした: {exc}")
    st.info("READMEの起動手順、ネットワーク接続、同じ索引を別プロセスで開いていないか確認してください。")
    st.stop()

documents=service.list_documents()
cols=st.columns(3)
cols[0].metric("登録資料",f"{len(documents)} 冊")
cols[1].metric("対象ページ",sum(d.page_count for d in documents))
cols[2].metric("回答モード","根拠原文" if settings.llm_provider=="extractive" else "外部API")
with st.sidebar:
    st.subheader("利用上の注意")
    st.write("ローカル・単一利用者向けの検証版です。設計判断、法規適合、部品選定の最終確認は技術者が行ってください。")
    st.caption("表の列・極数・負荷条件・脚注は原本でも確認してください。")
    if settings.llm_provider=="extractive":
        st.success("回答生成の外部API送信なし")
        st.caption("初回のEmbeddingモデル取得には通信します。")
    else:
        st.warning("質問と根拠本文を外部APIへ送信します。機密資料を登録しないでください。")
    with st.expander("検索設定"):
        st.write({"Embedding":settings.embedding_model,"最大根拠ページ":settings.top_k,"cosine閾値":settings.min_relevance_score})

search_tab,register_tab,quality_tab=st.tabs(["質問・根拠","資料の登録","品質と限界"])
with search_tab:
    if not documents:
        st.info("まず「資料の登録」で、自作サンプルを登録してください。")
    question=st.text_area("確認したい仕様",placeholder="例：PWR-240-24の定格出力電流は？",height=90)
    st.caption("型式、仕様項目、必要な条件を含めると確認しやすくなります。")
    if st.button("根拠を検索",type="primary",disabled=not documents,width="stretch"):
        try:
            with st.spinner("対象の型式・仕様・根拠を照合しています…"):
                st.session_state["answer"]=service.ask(question)
                st.session_state["answered_question"]=question
        except Exception as exc:
            st.error(f"検索できませんでした: {exc}")
    result=st.session_state.get("answer")
    if result:
        st.subheader(st.session_state["answered_question"])
        if not result.answerable:
            st.warning(result.answer)
            st.caption(result.refusal_reason or "根拠不足")
            st.write("資料に存在しないと断定した結果ではありません。抽出・検索・適用条件の確認に失敗した場合も拒否します。")
        else:
            st.success(f"確認用の根拠が {len(result.citations)} ページ見つかりました。")
            has_bound_values=any(c.hit.metadata.get('structured_facts') for c in result.citations)
            if settings.llm_provider!="extractive" or has_bound_values:
                st.text(result.answer)
            if settings.llm_provider=="extractive":
                st.caption("原文と、位置情報で対応を確認できた表の値を示します。設計判断は行いません。")
            for context in result.citations:
                hit=context.hit
                with st.container(border=True):
                    st.markdown(f"**{context.context_id}｜{hit.file_name}**")
                    st.caption(f"PDF物理ページ {hit.page_number}（印刷ページ番号とは異なる場合があります）")
                    if sum(d.file_name==hit.file_name for d in documents)>1:
                        st.caption(f"同名の別資料と区別する識別子: {hit.document_id[:8]}")
                    if hit.metadata.get('binding_proof_only'):
                        st.caption("型式と仕様列の対応を示す補助出典です。仕様値そのものの根拠とは区別しています。")
                    approved=hit.metadata.get('structured_facts',[])
                    facts=[{"model":f.get('display_model',f["model"]),"property":" ".join(f["original_label"].split())+" / "+('/'.join(f['conditions']) or ('原本の適用条件を参照' if f.get('binding') else '対象行共通')),"value":f["value"]}
                              for f in approved] if approved else list(hit.metadata.get("table_facts",[]))
                    if facts:
                        st.write("列が明示されている型式別のセル")
                        st.dataframe([{"型式":f["model"],"項目（原文）":f["property"],"値（原文）":f["value"]} for f in facts],hide_index=True,width="stretch")
                        st.caption("空セル・結合セルは推測補完していません。共通条件と脚注は原本を参照してください。")
                    bindings={(f['model'],f['binding']['page']):f['binding'] for f in hit.metadata.get('structured_facts',[]) if f.get('binding')}
                    for (model,page_number),binding in bindings.items():
                        reference=next((c.context_id for c in result.citations if c.hit.document_id==hit.document_id and c.hit.page_number==page_number),'')
                        same_page=page_number==hit.page_number
                        st.caption(f"{model}の対応根拠: {reference} / PDF {page_number}ページ / "+binding.get('summary',('明示された型式列' if same_page else '同じ見出し内で出力電圧・出力電流が一意に対応')))
                    with st.expander("根拠本文を読む",expanded=len(result.citations)==1 and not approved):
                        st.text(hit.text)
                    path=service.document_path(hit.document_id)
                    if path:
                        st.download_button("原本PDFを保存して確認",path.read_bytes(),file_name=hit.file_name,mime="application/pdf",key=f"pdf-{context.context_id}")
        with st.expander("検索候補（回答根拠とは限りません）"):
            for h in result.retrieved_hits:
                st.caption(f"{h.file_name} / PDF {h.page_number}ページ / cosine {h.score:.3f}")
                st.text(h.text[:300])
with register_tab:
    st.subheader("資料を追加")
    st.write("テキストを選択できるPDFが対象です。公開デモには自作資料だけを使ってください。")
    # A registration triggers a rerun to refresh the list. Keep its outcome
    # across that rerun, including a rejected/corrupt upload.
    for succeeded,message in st.session_state.get('registration_feedback',[]):
        (st.success if succeeded else st.error)(message)
    if st.button("自作サンプル3冊を登録（API不要）"):
        try:
            with st.spinner("登録中…"):
                for path in sorted((ROOT/"sample_data/pdfs").glob("*.pdf")):
                    service.ingest_pdf(path.name,path.read_bytes())
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    uploads=st.file_uploader("PDFを選択（複数可・1冊50MBまで）",type=["pdf"],accept_multiple_files=True)
    if st.button("選択した資料を登録",disabled=not uploads):
        feedback=[]
        for upload in uploads or []:
            try:
                with st.spinner(f"{upload.name}を登録中…"):
                    ingested=service.ingest_pdf(upload.name,upload.getvalue())
                feedback.append((True,f"{upload.name}: "+("登録済み（重複なし）" if ingested.already_registered else "登録完了")))
            except Exception as exc:
                feedback.append((False,f"{upload.name}: {exc}"))
        st.session_state['registration_feedback']=feedback
        st.session_state.pop("answer",None)
        st.rerun()
    st.subheader("登録資料一覧")
    st.dataframe([{"資料名":d.file_name,"ページ":d.page_count,"チャンク":d.chunk_count} for d in documents],hide_index=True,width="stretch")
    st.caption("スキャン、暗号化、破損PDFは対象外。異なる版を混在させると適用判断が難しくなります。")
with quality_tab:
    st.subheader("性能は、評価条件と一緒に見る")
    st.write("旧28問は変更せず比較しています。未知資料の初回結果と、修正後の再試験を分けて記録します。")
    public=ROOT/"docs/portfolio/metrics.json"
    if public.exists():
        measured=json.loads(public.read_text(encoding="utf-8"))
        fixed=measured['fixed_28']
        quality_cols=st.columns(3)
        quality_cols[0].metric("固定28問：可否正解",f"{fixed['answerability_accuracy']:.1%}")
        quality_cols[1].metric("答えなし5問：拒否",f"{fixed['unanswerable_refusal_rate']:.0%}")
        quality_cols[2].metric("新規資料10問：可否正解",f"{measured['MEAN_WELL_blind_first_pass_10']['answerability_accuracy']:.0%}")
        st.caption("新規資料はコード固定後の初回結果です。対象は電源資料で、他の製品カテゴリの性能を保証する数字ではありません。")
        with st.expander("評価条件と全指標"):
            st.json(measured)
    st.warning("ページ取得・引用一致の合格は、表の数値や適用条件の完全な正解を保証しません。")
    st.write("未解決：省略型式・別名、共通仕様の継承、結合セル、複雑な表の列対応、未知の仕様表現。")
    st.caption("この画面から行う評価は自作ダミー資料の8問です。外部APIモードではAPIを使用します。")
    if st.button("自作サンプル8問を評価"):
        try:
            with st.spinner("評価中…"):
                rows=evaluate(service,load_dataset(ROOT/"sample_data/evaluation.json"))
            st.json(summarize(rows))
            st.dataframe([{"ID":r.case_id,"可否正解":r.answerability_correct,"出典再現":r.source_recall,"合格":r.passed} for r in rows],hide_index=True)
        except Exception as exc:
            st.error(str(exc))

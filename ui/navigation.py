"""One navigation/selection contract, with no URL-based internal routing."""
import streamlit as st
from services import ui_adapter as adapter

PAGE = "ugfs_page"
SELECTED = "ugfs_selected_uid"


def initialize():
    st.session_state.setdefault(PAGE, "home")
    st.session_state.setdefault(SELECTED, None)


def navigate(page):
    st.session_state[PAGE] = page


def select_row(row):
    # Only an explicit row interaction reaches this callback. Merely displaying
    # the initial detail or switching pages never persists a read flag.
    st.session_state[SELECTED] = row["uid"]
    if not row["read"]:
        try:
            adapter.mark_read(row)
        except Exception as exc:
            st.session_state["ugfs_notice"] = ("error", str(exc))


def selected_row(rows):
    uid = st.session_state.get(SELECTED)
    if uid is None and rows:
        st.session_state[SELECTED] = rows[0]["uid"]
    return next((r for r in rows if r["uid"] == uid), rows[0] if rows else None)


def set_page_number(number):
    st.session_state["ugfs_list_page"] = number


def navigate_with_selection(page, uid):
    st.session_state[SELECTED] = uid
    if page in {'results', 'validation'}:
        st.session_state.pop('result_selected', None)
    navigate(page)


def navigate_to_result(uid, service=None, need_id='primary'):
    navigate_with_selection('results', uid)
    if service:
        st.session_state['result_selected'] = f'{uid}:{service}:{need_id}'


def navigate_to_diffusion(uid, service):
    if service in adapter.SERVICES:
        st.session_state["digest_service"] = service
    navigate_with_selection("diffusion", uid)


def execute(function, *args, **kwargs):
    """Common explicit-action feedback; read-only rendering never calls it."""
    try:
        with st.spinner("Traitement en cours…"):
            result = function(*args, **kwargs)
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool):
            success, message = result
        elif isinstance(result, dict):
            success = result.get("ok", not result.get("errors"))
            message = result.get("message") or " ; ".join(result.get("errors", [])) or "Opération terminée."
        else:
            from pathlib import Path
            if isinstance(result,(str,Path)) and str(result).lower().endswith('.xlsx') and Path(result).is_file():
                st.session_state['ugfs_notice_download']=str(result)
                success,message=True,'Export Excel généré'
            else:
                success, message = True, str(result or "Opération terminée.")
        st.session_state["ugfs_notice"] = ("success" if success else "error", str(message))
        return result
    except Exception as exc:
        st.session_state["ugfs_notice"] = ("error", str(exc))
        return None


def start_action(label, resource, name, *args, **kwargs):
    try:
        if name=='run_analysis' and args and args[0].get('document_status'):
            name='segment_bulletin';label='Analyse du bulletin CMF';resource='segmentation:'+args[0]['uid'];args=(args[0],);kwargs={}
        token = adapter.start_action(label, resource, name, *args, **kwargs)
        st.session_state.setdefault("ugfs_jobs", []).append(token)
        if name in {'run_analysis','segment_bulletin'} and args:
            row=args[0]
            st.session_state.setdefault('ugfs_job_context',{})[token]={'uid':row['uid'],'entity':row.get('entity',''),'title':row.get('title',''),'operation':'segmentation' if name=='segment_bulletin' else 'analysis','retry':(label,resource,name,args,kwargs)}
    except Exception as exc:
        st.session_state["ugfs_notice"] = ("warning" if "déjà en cours" in str(exc) else "error", str(exc))

"""SEO Change Log: manually record SEO actions taken on the site."""

from datetime import date

import streamlit as st

from database import change_log_repository, target_keyword_repository
from database.db_setup import initialize_database
from utils.constants import CHANGE_CATEGORIES

st.set_page_config(page_title="SEO Change Log", layout="wide")
initialize_database()
st.title("SEO Change Log")

st.subheader("Record a New SEO Change")
with st.form("change_log_form", clear_on_submit=True):
    change_date = st.date_input("Date", value=date.today())
    page_url = st.text_input("Page URL")
    category = st.selectbox("Change category", CHANGE_CATEGORIES)
    description = st.text_area("Description")
    target_keyword = st.text_input("Target keyword")
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Save change")

if submitted:
    if not page_url.strip():
        st.error("Page URL is required.")
    else:
        change_log_repository.add_change(change_date, page_url.strip(), category, description, target_keyword, notes)
        if target_keyword.strip():
            target_keyword_repository.add_target_keyword(target_keyword.strip())
            st.success(f"SEO change recorded. '{target_keyword.strip()}' is now tracked on the Keyword Performance page.")
        else:
            st.success("SEO change recorded.")

st.subheader("Change History")
changes_df = change_log_repository.list_changes()

if changes_df.empty:
    st.info("No SEO changes recorded yet.")
else:
    st.dataframe(changes_df, width="stretch", hide_index=True)

    st.subheader("Edit or Delete an Entry")
    selected_id = st.selectbox(
        "Select an entry",
        options=[None, *changes_df["id"].tolist()],
        format_func=lambda x: "Select an entry..." if x is None else f"#{x}",
    )

    if selected_id is not None:
        entry = changes_df[changes_df["id"] == selected_id].iloc[0]
        category_index = CHANGE_CATEGORIES.index(entry["category"]) if entry["category"] in CHANGE_CATEGORIES else 0

        with st.form("edit_change_form"):
            edit_date = st.date_input("Date", value=date.fromisoformat(entry["change_date"]))
            edit_page_url = st.text_input("Page URL", value=entry["page_url"])
            edit_category = st.selectbox("Change category", CHANGE_CATEGORIES, index=category_index)
            edit_description = st.text_area("Description", value=entry["description"] or "")
            edit_target_keyword = st.text_input("Target keyword", value=entry["target_keyword"] or "")
            edit_notes = st.text_area("Notes", value=entry["notes"] or "")
            save_edit = st.form_submit_button("Save changes")

        if save_edit:
            if not edit_page_url.strip():
                st.error("Page URL is required.")
            else:
                change_log_repository.update_change(
                    selected_id, edit_date, edit_page_url.strip(), edit_category, edit_description, edit_target_keyword, edit_notes
                )
                if edit_target_keyword.strip():
                    target_keyword_repository.add_target_keyword(edit_target_keyword.strip())
                st.success("SEO change updated.")
                st.rerun()

        if st.button("Delete this entry"):
            change_log_repository.delete_change(selected_id)
            st.rerun()

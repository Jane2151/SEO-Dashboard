"""SEO Change Log: manually record SEO actions taken on the site."""

from datetime import date
from urllib.parse import urlparse

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
    categories = st.multiselect("Change category", CHANGE_CATEGORIES)
    description = st.text_area("Description")
    target_keyword = st.text_input("Target keyword")
    notes = st.text_area("Notes")
    submitted = st.form_submit_button("Save change")

if submitted:
    if not page_url.strip():
        st.error("Page URL is required.")
    elif not categories:
        st.error("Select at least one change category.")
    else:
        category = ", ".join(categories)
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
    # Split the stored "A, B, C" string back into a list so st.dataframe
    # renders each category as its own bordered tag instead of one long,
    # truncated string.
    display_df = changes_df.copy()
    display_df["category"] = display_df["category"].apply(lambda c: [part.strip() for part in (c or "").split(",") if part.strip()])
    # Every entry is on the same site, so the domain is repeated noise —
    # showing just the path frees up real width for the page url column,
    # which otherwise crowds out Description (the more useful field) or
    # gets truncated itself.
    display_df["page_url"] = display_df["page_url"].apply(lambda u: (urlparse(u).path or "/") if u else u)

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        # id and created_at are bookkeeping, not about the change itself —
        # dropped so the remaining columns fit without a horizontal scroll,
        # which reset (and so had to be redone) on every rerun anyway. Full
        # detail, including these two, is still available by picking the
        # entry below.
        column_order=["change_date", "category", "target_keyword", "description", "page_url", "notes"],
        column_config={
            "change_date": st.column_config.TextColumn("Date", width="small"),
            "category": st.column_config.MultiselectColumn("Category", options=CHANGE_CATEGORIES, width=200),
            "target_keyword": st.column_config.TextColumn("Target Keyword", width=100),
            "description": st.column_config.TextColumn("Description", width=270),
            "page_url": st.column_config.TextColumn("Page URL (path)", width=130),
            "notes": st.column_config.TextColumn("Notes", width=80),
        },
    )

    st.subheader("Edit or Delete an Entry")
    selected_id = st.selectbox(
        "Select an entry",
        options=[None, *changes_df["id"].tolist()],
        format_func=lambda x: "Select an entry..." if x is None else f"#{x}",
    )

    if selected_id is not None:
        entry = changes_df[changes_df["id"] == selected_id].iloc[0]
        existing_categories = [c.strip() for c in (entry["category"] or "").split(",") if c.strip()]
        default_categories = [c for c in existing_categories if c in CHANGE_CATEGORIES]

        with st.form("edit_change_form"):
            edit_date = st.date_input("Date", value=date.fromisoformat(entry["change_date"]))
            edit_page_url = st.text_input("Page URL", value=entry["page_url"])
            edit_categories = st.multiselect("Change category", CHANGE_CATEGORIES, default=default_categories)
            edit_description = st.text_area("Description", value=entry["description"] or "")
            edit_target_keyword = st.text_input("Target keyword", value=entry["target_keyword"] or "")
            edit_notes = st.text_area("Notes", value=entry["notes"] or "")
            save_edit = st.form_submit_button("Save changes")

        if save_edit:
            if not edit_page_url.strip():
                st.error("Page URL is required.")
            elif not edit_categories:
                st.error("Select at least one change category.")
            else:
                edit_category = ", ".join(edit_categories)
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

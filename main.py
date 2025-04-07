import streamlit as st
import pypdf
import os
import re
import zipfile
import io
import tempfile
import pandas as pd

# Helper function to sanitize chapter names for use as filenames
def sanitize_filename(name):
    # Remove invalid characters
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Truncate if too long (optional)
    return name[:100]

# Function to extract potential chapter names, primarily from bookmarks
def extract_potential_chapters(pdf_reader):
    """
    Attempts to extract chapter titles and their starting pages from PDF bookmarks.
    Returns a list of tuples: [(title, start_page_num), ...]
    Page numbers are 1-based for user display.
    """
    chapters = []
    try:
        # Use outline (bookmarks) if available - this is the most reliable
        for item in pdf_reader.outline:
            # Handle nested bookmarks - often only top-level are chapters
            if isinstance(item, pypdf.generic.Destination):
                 # Sometimes the title is indirect, try resolving it
                title = item.title
                try:
                    # Resolve indirect object if necessary
                    if isinstance(title, pypdf.generic.IndirectObject):
                         resolved_title = pdf_reader.get_object(title)
                         if isinstance(resolved_title, pypdf.generic.TextStringObject):
                             title = resolved_title.strip()
                         else:
                             title = f"Unknown Title (Obj {title.idnum})" # Fallback
                    elif isinstance(title, pypdf.generic.TextStringObject):
                         title = title.strip()
                    else:
                         title = f"Unknown Title (Type {type(title)})" # Fallback

                    # Get page number (0-based) and convert to 1-based
                    page_num_0based = pdf_reader.get_page_number(item.page)
                    if page_num_0based is not None:
                        chapters.append((title, page_num_0based + 1))
                except Exception as e:
                    st.warning(f"Could not fully process bookmark item '{getattr(item, 'title', 'N/A')}': {e}")
            # If it's a list, it might represent nested bookmarks.
            # You could recursively process `item` here if needed,
            # but for simplicity, we'll often just take the top level.
            elif isinstance(item, list):
                 # Try processing the first item in the nested list if it exists
                 if item:
                     first_sub_item = item[0]
                     if isinstance(first_sub_item, pypdf.generic.Destination):
                         try:
                             title = first_sub_item.title
                             if isinstance(title, pypdf.generic.IndirectObject):
                                 resolved_title = pdf_reader.get_object(title)
                                 if isinstance(resolved_title, pypdf.generic.TextStringObject):
                                     title = resolved_title.strip()
                                 else:
                                     title = f"Unknown Nested Title (Obj {title.idnum})"
                             elif isinstance(title, pypdf.generic.TextStringObject):
                                 title = title.strip()
                             else:
                                 title = f"Unknown Nested Title (Type {type(title)})"

                             page_num_0based = pdf_reader.get_page_number(first_sub_item.page)
                             if page_num_0based is not None:
                                 chapters.append((f"{title} (Nested)", page_num_0based + 1)) # Indicate it was nested
                         except Exception as e:
                             st.warning(f"Could not fully process nested bookmark item '{getattr(first_sub_item, 'title', 'N/A')}': {e}")


        if chapters:
            st.success("Extracted potential chapters from PDF bookmarks.")
            # Sort by page number just in case bookmarks are out of order
            chapters.sort(key=lambda x: x[1])
            return chapters
        else:
            st.info("No bookmarks found in the PDF. Please define chapters manually.")
            return []

    except Exception as e:
        st.error(f"Error reading PDF outline (bookmarks): {e}")
        return []

# Function to split the PDF based on defined chapters
def split_pdf(pdf_reader, chapter_definitions, output_dir):
    """
    Splits the PDF into multiple files based on chapter definitions.
    chapter_definitions: List of dicts [{'Chapter Name': name, 'Start Page': start, 'End Page': end}, ...]
    Returns a list of paths to the created chapter PDFs.
    """
    output_files = []
    total_pages = len(pdf_reader.pages)

    for i, chapter in enumerate(chapter_definitions):
        name = chapter.get('Chapter Name', f'Chapter_{i+1}')
        start_page = chapter.get('Start Page')
        end_page = chapter.get('End Page')

        # Validate page numbers
        if not isinstance(start_page, int) or not isinstance(end_page, int):
            st.warning(f"Skipping chapter '{name}': Invalid page numbers (must be integers).")
            continue
        if not (1 <= start_page <= total_pages and 1 <= end_page <= total_pages):
            st.warning(f"Skipping chapter '{name}': Page numbers ({start_page}-{end_page}) out of range (1-{total_pages}).")
            continue
        if start_page > end_page:
            st.warning(f"Skipping chapter '{name}': Start page ({start_page}) is after end page ({end_page}).")
            continue

        sanitized_name = sanitize_filename(name)
        output_filename = os.path.join(output_dir, f"{i+1:02d}_{sanitized_name}.pdf")

        try:
            writer = pypdf.PdfWriter()
            # Remember pypdf pages are 0-indexed, user input is 1-based
            for page_num in range(start_page - 1, end_page):
                writer.add_page(pdf_reader.pages[page_num])

            with open(output_filename, "wb") as output_pdf:
                writer.write(output_pdf)
            output_files.append(output_filename)
            # st.write(f"Successfully created: {os.path.basename(output_filename)}") # Optional progress update
        except Exception as e:
            st.error(f"Failed to create PDF for chapter '{name}': {e}")

    return output_files

# --- Streamlit App ---
st.set_page_config(layout="wide")
st.title("📄 PDF Chapter Splitter")
st.markdown("""
Upload a PDF file. The application will attempt to detect chapters using PDF bookmarks.
You can then review and adjust the chapter names and page ranges before splitting the PDF
into separate files, one for each chapter.
""")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    try:
        pdf_bytes = uploaded_file.getvalue()
        pdf_reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(pdf_reader.pages)
        st.info(f"PDF loaded: '{uploaded_file.name}' ({total_pages} pages)")

        potential_chapters = extract_potential_chapters(pdf_reader)

        # --- Chapter Definition Area ---
        st.subheader("Define Chapters and Page Ranges")
        st.markdown(f"Total pages in PDF: **{total_pages}**. Please define the start and end page for each chapter.")

        # Prepare data for the editable table
        if 'chapter_data' not in st.session_state or st.session_state.get('pdf_name') != uploaded_file.name:
            st.session_state.pdf_name = uploaded_file.name # Track the current PDF
            initial_data = []
            if potential_chapters:
                for i, (title, start_page) in enumerate(potential_chapters):
                    # Guess end page based on next chapter's start page
                    end_page = total_pages # Default for last chapter
                    if i + 1 < len(potential_chapters):
                        end_page = potential_chapters[i+1][1] - 1
                    # Ensure end page is not before start page (can happen with overlapping bookmarks)
                    if end_page < start_page:
                         end_page = start_page # Set end = start if overlap detected

                    initial_data.append({
                        "Chapter Name": title,
                        "Start Page": start_page,
                        "End Page": end_page
                    })
            else:
                # Provide a default row if no chapters were detected
                initial_data.append({
                    "Chapter Name": "Chapter 1",
                    "Start Page": 1,
                    "End Page": total_pages
                })
            st.session_state.chapter_data = pd.DataFrame(initial_data)

        # Display editable table using st.data_editor
        edited_df = st.data_editor(
            st.session_state.chapter_data,
            num_rows="dynamic", # Allow adding/deleting rows
            column_config={
                "Chapter Name": st.column_config.TextColumn("Chapter Name", required=True, help="Name for the chapter file"),
                "Start Page": st.column_config.NumberColumn("Start Page", min_value=1, max_value=total_pages, step=1, required=True, help="First page of the chapter (1-based)"),
                "End Page": st.column_config.NumberColumn("End Page", min_value=1, max_value=total_pages, step=1, required=True, help="Last page of the chapter (1-based)"),
            },
            key="chapter_editor" # Assign a key to persist edits
        )

        # --- Splitting Execution ---
        st.subheader("Split PDF")
        if st.button("Split PDF into Chapters", key="split_button"):
            # Convert DataFrame back to list of dicts for processing
            chapter_definitions = edited_df.to_dict('records')

            if not chapter_definitions:
                st.warning("Please define at least one chapter.")
            else:
                # Create a temporary directory to store split files
                with tempfile.TemporaryDirectory() as temp_dir:
                    st.info("Splitting PDF... Please wait.")
                    progress_bar = st.progress(0)

                    # Re-read the PDF reader just in case (though usually not needed for reading)
                    pdf_reader_process = pypdf.PdfReader(io.BytesIO(pdf_bytes))
                    output_pdf_files = split_pdf(pdf_reader_process, chapter_definitions, temp_dir)

                    progress_bar.progress(50) # Update progress

                    if output_pdf_files:
                        # Create a zip file containing all chapter PDFs
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                            for i, file_path in enumerate(output_pdf_files):
                                arcname = os.path.basename(file_path) # Name inside the zip
                                zip_file.write(file_path, arcname=arcname)
                                progress_bar.progress(50 + int(50 * (i + 1) / len(output_pdf_files))) # Update progress per file

                        zip_buffer.seek(0)
                        st.success(f"Successfully split the PDF into {len(output_pdf_files)} chapter files.")

                        # Provide download button for the zip file
                        st.download_button(
                            label="Download All Chapters (.zip)",
                            data=zip_buffer,
                            file_name=f"{os.path.splitext(uploaded_file.name)[0]}_chapters.zip",
                            mime="application/zip",
                            key="download_zip"
                        )
                    else:
                        st.error("No chapter PDFs were generated. Please check chapter definitions and page ranges.")
                    progress_bar.empty() # Remove progress bar

    except Exception as e:
        st.error(f"An error occurred processing the PDF: {e}")
        st.exception(e) # Show detailed traceback for debugging

else:
    st.info("Please upload a PDF file to begin.")

# Add some footer or info
st.markdown("---")
st.markdown("Created with Streamlit and pypdf.")
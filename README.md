# PDF Chapter Splitter

A Streamlit web application to split PDF files into chapters based on bookmarks or user-defined page ranges.

## Description

This application allows you to upload a PDF file and split it into multiple smaller PDF files, each representing a chapter. It attempts to automatically detect chapter boundaries using the bookmarks (outline) present in the PDF. If no bookmarks are found, or if you need to adjust the chapter definitions, you can manually edit the chapter names and their corresponding start and end page numbers in an interactive table. Finally, you can download all the split chapters as a single ZIP file.

**Key Features:**

* **Easy-to-use web interface** built with Streamlit.
* **Automatic chapter detection** from PDF bookmarks.
* **Interactive chapter definition table** for manual adjustments.
* **Clear display** of total pages and detected/defined chapters.
* **Sanitized filenames** for chapter PDFs.
* **Download all chapters** as a convenient ZIP archive.
* **Error handling** for common PDF processing issues.

## Installation

Before running the application, you need to have Python installed on your system. You also need to install the required Python libraries. You can do this using pip:

```bash
pip install streamlit pypdf pandas

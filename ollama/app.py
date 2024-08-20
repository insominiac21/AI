import streamlit as st
import logging
import os
import tempfile
import shutil
import pdfplumber
import requests
import ollama

from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_community.embeddings import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_models import ChatOllama
from langchain_core.runnables import RunnablePassthrough
from langchain.retrievers.multi_query import MultiQueryRetriever
from typing import List, Tuple, Dict, Any, Optional

# Streamlit page configuration
st.set_page_config(
    page_title="Ollama PDF RAG Streamlit UI",
    page_icon="🎈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

@st.cache_resource(show_spinner=True)
def extract_model_names(
    models_info: Dict[str, List[Dict[str, Any]]],
) -> Tuple[str, ...]:
    logger.info("Extracting model names from models_info")
    model_names = tuple(model["name"] for model in models_info["models"])
    logger.info(f"Extracted model names: {model_names}")
    return model_names

def download_arxiv_pdf(arxiv_id: str, save_dir: str) -> str:
    """
    Download a PDF from arXiv using the given arXiv ID.

    Args:
        arxiv_id (str): The arXiv ID of the paper to download.
        save_dir (str): Directory to save the downloaded PDF.

    Returns:
        str: Path to the downloaded PDF.
    """
    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    response = requests.get(url)
    if response.status_code == 200:
        pdf_path = os.path.join(save_dir, f"{arxiv_id}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(response.content)
        return pdf_path
    else:
        raise Exception(f"Failed to download PDF. Status code: {response.status_code}")

def create_vector_db(file_upload=None, pdf_path=None) -> Chroma:
    """
    Create a vector database from an uploaded or downloaded PDF file.

    Args:
        file_upload (st.UploadedFile): Streamlit file upload object containing the PDF.
        pdf_path (str): Path to the downloaded PDF file.

    Returns:
        Chroma: A vector store containing the processed document chunks.
    """
    logger.info(f"Creating vector DB from file: {file_upload.name if file_upload else pdf_path}")
    temp_dir = tempfile.mkdtemp()

    if file_upload:
        path = os.path.join(temp_dir, file_upload.name)
        with open(path, "wb") as f:
            f.write(file_upload.getvalue())
    else:
        path = pdf_path

    loader = UnstructuredPDFLoader(path)
    data = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=7500, chunk_overlap=100)
    chunks = text_splitter.split_documents(data)
    logger.info("Document split into chunks")

    embeddings = OllamaEmbeddings(model="nomic-embed-text", show_progress=True)
    vector_db = Chroma.from_documents(
        documents=chunks, embedding=embeddings, collection_name="myRAG"
    )
    logger.info("Vector DB created")

    shutil.rmtree(temp_dir)
    logger.info(f"Temporary directory {temp_dir} removed")
    return vector_db

def process_question(question: str, vector_db: Chroma, selected_model: str) -> str:
    logger.info(f"""Processing question: {
                question} using model: {selected_model}""")
    llm = ChatOllama(model=selected_model, temperature=0)
    QUERY_PROMPT = PromptTemplate(
        input_variables=["question"],
        template="""You are an AI language model assistant. Your task is to generate 3
        different versions of the given user question to retrieve relevant documents from
        a vector database. By generating multiple perspectives on the user question, your
        goal is to help the user overcome some of the limitations of the distance-based
        similarity search. Provide these alternative questions separated by newlines.
        Original question: {question}""",
    )

    retriever = MultiQueryRetriever.from_llm(
        vector_db.as_retriever(), llm, prompt=QUERY_PROMPT
    )

    template = """Answer the question based ONLY on the following context:
    {context}
    Question: {question}
    If you don't know the answer, just say that you don't know, don't try to make up an answer.
    Only provide the answer from the {context}, nothing else.
    Add snippets of the context you used to answer the question.
    """

    prompt = ChatPromptTemplate.from_template(template)

    chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    response = chain.invoke(question)
    logger.info("Question processed and response generated")
    return response

@st.cache_data
def extract_all_pages_as_images(file_upload) -> List[Any]:
    logger.info(f"""Extracting all pages as images from file: {
                file_upload.name}""")
    pdf_pages = []
    with pdfplumber.open(file_upload) as pdf:
        pdf_pages = [page.to_image().original for page in pdf.pages]
    logger.info("PDF pages extracted as images")
    return pdf_pages

def delete_vector_db(vector_db: Optional[Chroma]) -> None:
    logger.info("Deleting vector DB")
    if vector_db is not None:
        vector_db.delete_collection()
        st.session_state.pop("pdf_pages", None)
        st.session_state.pop("file_upload", None)
        st.session_state.pop("vector_db", None)
        st.success("Collection and temporary files deleted successfully.")
        logger.info("Vector DB and related session state cleared")
        st.rerun()
    else:
        st.error("No vector database found to delete.")
        logger.warning("Attempted to delete vector DB, but none was found")

def main() -> None:
    st.subheader("🧠 Ollama PDF RAG playground", divider="gray", anchor=False)

    models_info = ollama.list()
    available_models = extract_model_names(models_info)

    col1, col2 = st.columns([1.5, 2])

    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if "vector_db" not in st.session_state:
        st.session_state["vector_db"] = None

    if available_models:
        selected_model = col2.selectbox(
            "Pick a model available locally on your system ↓", available_models
        )

    arxiv_id = col1.text_input("Enter arXiv ID to download the PDF ↓", "")
    file_upload = col1.file_uploader(
        "Or upload a PDF file ↓", type="pdf", accept_multiple_files=False
    )

    if arxiv_id:
        with st.spinner("Downloading and processing the PDF..."):
            try:
                temp_dir = tempfile.mkdtemp()
                pdf_path = download_arxiv_pdf(arxiv_id, temp_dir)
                st.session_state["vector_db"] = create_vector_db(pdf_path=pdf_path)
                pdf_pages = extract_all_pages_as_images(open(pdf_path, "rb"))
                st.session_state["pdf_pages"] = pdf_pages
                shutil.rmtree(temp_dir)
            except Exception as e:
                st.error(f"Error downloading or processing the PDF: {e}")

    elif file_upload:
        st.session_state["file_upload"] = file_upload
        if st.session_state["vector_db"] is None:
            st.session_state["vector_db"] = create_vector_db(file_upload=file_upload)
        pdf_pages = extract_all_pages_as_images(file_upload)
        st.session_state["pdf_pages"] = pdf_pages

    if "pdf_pages" in st.session_state:
        zoom_level = col1.slider(
            "Zoom Level", min_value=100, max_value=1000, value=700, step=50
        )

        with col1:
            with st.container(height=410, border=True):
                for page_image in st.session_state["pdf_pages"]:
                    st.image(page_image, width=zoom_level)

    delete_collection = col1.button("⚠ Delete collection", type="secondary")

    if delete_collection:
        delete_vector_db(st.session_state["vector_db"])

    with col2:
        message_container = st.container(height=500, border=True)

        for message in st.session_state["messages"]:
            avatar = "🤖" if message["role"] == "assistant" else "😎"
            with message_container.chat_message(message["role"], avatar=avatar):
                st.markdown(message["content"])

        if prompt := st.chat_input("Enter a prompt here..."):
            try:
                st.session_state["messages"].append({"role": "user", "content": prompt})
                with st.spinner("Generating response..."):
                    if st.session_state["vector_db"] is not None:
                        response = process_question(
                            prompt, st.session_state["vector_db"], selected_model
                        )
                        st.session_state["messages"].append(
                            {"role": "assistant", "content": response}
                        )
                    else:
                        st.error("Please upload a PDF file first.")
            except Exception as e:
                st.error(f"Error processing the question: {e}")

if __name__ == "__main__":
    main()
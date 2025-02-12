from sentence_transformers import SentenceTransformer
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import CharacterTextSplitter
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from langchain_core.embeddings import Embeddings

# Create a custom embedding class that implements Langchain's Embedding interface
class SentenceTransformerEmbeddings(Embeddings):
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_documents(self, texts):
        """Compute embeddings for a list of texts."""
        embeddings = self.model.encode(texts)
        return embeddings.tolist()

    def embed_query(self, text):
        """Compute embedding for a single text."""
        embedding = self.model.encode([text])[0]
        return embedding.tolist()

# Initialize sentence transformer embeddings
embeddings_model = SentenceTransformerEmbeddings()

# Initialize FAISS vector store (in-memory)
vector_store = FAISS.from_texts(["test"], embeddings_model)
vector_store.delete([vector_store.index_to_docstore_id[0]])

def compute_embeddings(texts):
    """Compute embeddings for a list of texts using Sentence Transformers."""
    return embeddings_model.embed_documents(texts)

def compute_similarity_matrix(embeddings):
    """Compute the cosine similarity matrix for the given embeddings."""
    return cosine_similarity(embeddings)

def semantic_chunking(texts, similarity_threshold=0.7, min_chunk_size=100, max_chunk_size=1000):
    """
    Perform semantic chunking on the given texts.
    
    Args:
    texts (list): List of text strings to chunk.
    similarity_threshold (float): Threshold for cosine similarity to consider texts as similar.
    min_chunk_size (int): Minimum number of characters in a chunk.
    max_chunk_size (int): Maximum number of characters in a chunk.
    
    Returns:
    list: List of semantically chunked texts.
    """
    embeddings = compute_embeddings(texts)
    similarity_matrix = compute_similarity_matrix(embeddings)
    
    chunks = []
    current_chunk = []
    current_chunk_size = 0
    
    for i, text in enumerate(texts):
        if current_chunk_size + len(text) > max_chunk_size:
            chunk = " ".join(current_chunk)
            chunks.append(chunk)
            current_chunk = []
            current_chunk_size = 0
        
        if not current_chunk:
            current_chunk.append(text)
            current_chunk_size += len(text)
        else:
            avg_similarity = np.mean([similarity_matrix[i][j] for j in range(i-len(current_chunk), i)])
            if avg_similarity >= similarity_threshold:
                current_chunk.append(text)
                current_chunk_size += len(text)
            else:
                if current_chunk_size >= min_chunk_size:
                    chunk = " ".join(current_chunk)
                    chunks.append(chunk)
                    current_chunk = [text]
                    current_chunk_size = len(text)
                else:
                    current_chunk.append(text)
                    current_chunk_size += len(text)
    
    if current_chunk:
        chunk = " ".join(current_chunk)
        chunks.append(chunk)
    
    return chunks

def second_stage_chunking(text, max_chunk_size=5000):
    """
    Break down a large chunk of text into smaller chunks.
    """
    text_splitter = CharacterTextSplitter(
        separator="\n",
        chunk_size=max_chunk_size,
        chunk_overlap=100,
        length_function=len
    )
    return text_splitter.split_text(text)

def smart_chunk_selection(chunks_per_user, max_total_chunks=100):
    """
    Select a balanced representation of chunks from each user's journey.
    """
    total_users = len(chunks_per_user)
    chunks_per_user_limit = max(1, max_total_chunks // total_users)
    
    selected_chunks = []
    for user_chunks in chunks_per_user:
        # Select evenly spaced chunks to represent the user's journey
        step = max(1, len(user_chunks) // chunks_per_user_limit)
        selected_chunks.extend(user_chunks[::step][:chunks_per_user_limit])
    
    # If we still have too many chunks, trim evenly
    while len(selected_chunks) > max_total_chunks:
        selected_chunks = selected_chunks[::2]
    
    return selected_chunks

def embed_and_store_data(texts: list[str]):
    """
    Embed the returned data using two-stage chunking and store it in vector store.
    """
    first_stage_chunks = semantic_chunking(texts)
    
    second_stage_chunks_per_user = [second_stage_chunking(chunk) for chunk in first_stage_chunks]
    
    selected_chunks = smart_chunk_selection(second_stage_chunks_per_user)

    vector_store.add_texts(selected_chunks)

async def get_chunks(user_activity_list, user_question):
    """
    Get relevant documents based on user question and selected events.
    """

    embed_and_store_data(user_activity_list)
    
    retriever = vector_store.as_retriever(search_type="mmr", search_kwargs={"k": 20, "fetch_k": 5000})

    # Test retrieval
    test_docs = retriever.get_relevant_documents(user_question)

    return test_docs
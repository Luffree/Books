import streamlit as st
import sqlite3
import requests
import pandas as pd
import uuid
from datetime import date, datetime

# ─── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Minha Biblioteca Virtual",
    page_icon="📚",
    layout="wide",
)

PLACEHOLDER_IMG = "https://via.placeholder.com/128x192.png?text=Sem+Capa"
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"
STATUS_OPTIONS = ["Quero Ler", "Lendo", "Lido", "Abandonado"]
STAR_MAP = {1: "⭐", 2: "⭐⭐", 3: "⭐⭐⭐", 4: "⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐"}

# ─── Database ─────────────────────────────────────────────────────────────────

def get_conn():
    return sqlite3.connect("biblioteca.db", check_same_thread=False)


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS livros (
                id            TEXT PRIMARY KEY,
                titulo        TEXT NOT NULL,
                autor         TEXT,
                ano           TEXT,
                genero        TEXT,
                sinopse       TEXT,
                capa_url      TEXT,
                status_leitura TEXT DEFAULT 'Quero Ler',
                nota          INTEGER,
                data_inicio   TEXT,
                data_fim      TEXT
            )
        """)
        conn.commit()


def insert_book(book: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO livros
                (id, titulo, autor, ano, genero, sinopse, capa_url,
                 status_leitura, nota, data_inicio, data_fim)
            VALUES
                (:id, :titulo, :autor, :ano, :genero, :sinopse, :capa_url,
                 :status_leitura, :nota, :data_inicio, :data_fim)
        """, book)
        conn.commit()


def delete_book(book_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM livros WHERE id = ?", (book_id,))
        conn.commit()


def load_books(status_filter=None, genero_filter=None) -> pd.DataFrame:
    query = "SELECT * FROM livros WHERE 1=1"
    params = []
    if status_filter and status_filter != "Todos":
        query += " AND status_leitura = ?"
        params.append(status_filter)
    if genero_filter and genero_filter != "Todos":
        query += " AND genero = ?"
        params.append(genero_filter)
    query += " ORDER BY titulo"
    with get_conn() as conn:
        df = pd.read_sql_query(query, conn, params=params)
    return df


def get_distinct_generos() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT genero FROM livros WHERE genero IS NOT NULL AND genero != '' ORDER BY genero"
        ).fetchall()
    return [r[0] for r in rows]


# ─── Google Books API ──────────────────────────────────────────────────────────

def search_google_books(query: str) -> list:
    try:
        resp = requests.get(
            GOOGLE_BOOKS_URL,
            params={"q": query, "maxResults": 10, "langRestrict": "pt"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("items", [])
    except requests.exceptions.Timeout:
        st.error("Tempo esgotado ao contatar a API do Google Books. Tente novamente.")
        return []
    except requests.exceptions.ConnectionError:
        st.error("Sem conexão com a internet. Verifique sua rede.")
        return []
    except Exception as e:
        st.error(f"Erro ao buscar livros: {e}")
        return []


def parse_volume(item: dict) -> dict:
    info = item.get("volumeInfo", {})
    images = info.get("imageLinks", {})
    capa = (
        images.get("thumbnail")
        or images.get("smallThumbnail")
        or PLACEHOLDER_IMG
    )
    # force HTTPS
    capa = capa.replace("http://", "https://")
    authors = info.get("authors", [])
    published = info.get("publishedDate", "")
    ano = published[:4] if published else ""
    return {
        "id": item.get("id", str(uuid.uuid4())),
        "titulo": info.get("title", "Sem título"),
        "autor": ", ".join(authors) if authors else "Desconhecido",
        "ano": ano,
        "genero": ", ".join(info.get("categories", [])),
        "sinopse": info.get("description", ""),
        "capa_url": capa,
    }


# ─── UI helpers ───────────────────────────────────────────────────────────────

def reading_form(prefix: str, book: dict):
    """Renders the save-to-library form inside an expander row."""
    with st.form(key=f"form_{prefix}_{book['id']}"):
        col1, col2 = st.columns(2)
        with col1:
            status = st.selectbox("Status", STATUS_OPTIONS, key=f"status_{prefix}_{book['id']}")
            nota = st.slider("Nota (estrelas)", 1, 5, 3, key=f"nota_{prefix}_{book['id']}")
        with col2:
            d_inicio = st.date_input("Data de início", value=None, key=f"di_{prefix}_{book['id']}")
            d_fim = st.date_input("Data de fim", value=None, key=f"df_{prefix}_{book['id']}")

        submitted = st.form_submit_button("💾 Salvar na Biblioteca")
        if submitted:
            book.update({
                "status_leitura": status,
                "nota": nota,
                "data_inicio": str(d_inicio) if d_inicio else None,
                "data_fim": str(d_fim) if d_fim else None,
            })
            insert_book(book)
            st.success(f'"{book["titulo"]}" salvo com sucesso!')


def render_stars(nota):
    if nota and int(nota) in STAR_MAP:
        return STAR_MAP[int(nota)]
    return "Sem avaliação"


def render_library_card(row):
    """Renders a single book card in the library grid."""
    capa = row.get("capa_url") or PLACEHOLDER_IMG
    titulo = row.get("titulo", "")
    autor = row.get("autor", "")
    status = row.get("status_leitura", "")
    nota = row.get("nota")
    d_inicio = row.get("data_inicio", "")
    d_fim = row.get("data_fim", "")
    book_id = row.get("id", "")

    st.image(capa, width=120)
    st.markdown(f"**{titulo}**")
    st.caption(f"_{autor}_")
    st.markdown(f"📖 {status}")
    st.markdown(render_stars(nota))
    if d_inicio:
        st.caption(f"Início: {d_inicio}")
    if d_fim:
        st.caption(f"Fim: {d_fim}")
    if st.button("🗑️ Excluir", key=f"del_{book_id}"):
        delete_book(book_id)
        st.success("Livro removido!")
        st.rerun()


# ─── Tabs ─────────────────────────────────────────────────────────────────────

def tab_buscar():
    st.header("🔍 Buscar e Adicionar Livros")
    query = st.text_input("Digite o título, autor ou ISBN:", placeholder="Ex: Dom Casmurro")

    if not query:
        st.info("Digite algo no campo acima para buscar livros via Google Books.")
        return

    with st.spinner("Buscando..."):
        items = search_google_books(query)

    if not items:
        st.warning("Nenhum resultado encontrado. Tente outros termos.")
        return

    st.markdown(f"**{len(items)} resultado(s) encontrado(s):**")

    for item in items:
        book = parse_volume(item)
        with st.container():
            cols = st.columns([1, 4])
            with cols[0]:
                st.image(book["capa_url"], width=90)
            with cols[1]:
                st.markdown(f"### {book['titulo']}")
                st.markdown(f"**Autor:** {book['autor']}  |  **Ano:** {book['ano']}  |  **Gênero:** {book['genero']}")
                sinopse = book["sinopse"]
                if sinopse:
                    st.caption(sinopse[:300] + ("..." if len(sinopse) > 300 else ""))
                with st.expander("➕ Adicionar à minha biblioteca"):
                    reading_form("search", book)
            st.divider()


def tab_manual():
    st.header("✏️ Cadastro Manual")
    st.markdown("Cadastre livros que não estão na API do Google Books.")

    with st.form("form_manual"):
        col1, col2 = st.columns(2)
        with col1:
            titulo = st.text_input("Título *", placeholder="Ex: O Senhor dos Anéis")
            autor = st.text_input("Autor", placeholder="Ex: J.R.R. Tolkien")
            ano = st.text_input("Ano de Publicação", placeholder="Ex: 1954")
            genero = st.text_input("Gênero", placeholder="Ex: Fantasia")
        with col2:
            status = st.selectbox("Status de Leitura", STATUS_OPTIONS)
            nota = st.slider("Nota (estrelas)", 1, 5, 3)
            d_inicio = st.date_input("Data de Início", value=None)
            d_fim = st.date_input("Data de Fim", value=None)

        capa_url = st.text_input("URL da Capa (opcional)", placeholder="https://...")
        sinopse = st.text_area("Sinopse", placeholder="Escreva um resumo do livro...")

        submitted = st.form_submit_button("💾 Salvar na Biblioteca")
        if submitted:
            if not titulo.strip():
                st.error("O campo Título é obrigatório.")
            else:
                book = {
                    "id": str(uuid.uuid4()),
                    "titulo": titulo.strip(),
                    "autor": autor.strip(),
                    "ano": ano.strip(),
                    "genero": genero.strip(),
                    "sinopse": sinopse.strip(),
                    "capa_url": capa_url.strip() or PLACEHOLDER_IMG,
                    "status_leitura": status,
                    "nota": nota,
                    "data_inicio": str(d_inicio) if d_inicio else None,
                    "data_fim": str(d_fim) if d_fim else None,
                }
                insert_book(book)
                st.success(f'"{titulo}" adicionado à sua biblioteca!')
                st.balloons()


def tab_biblioteca():
    st.header("📚 Minha Biblioteca")

    # Sidebar filters
    with st.sidebar:
        st.markdown("## 🔎 Filtros")
        status_filter = st.selectbox(
            "Status de Leitura",
            ["Todos"] + STATUS_OPTIONS,
        )
        generos = ["Todos"] + get_distinct_generos()
        genero_filter = st.selectbox("Gênero", generos)

    df = load_books(status_filter, genero_filter)

    if df.empty:
        st.info("Nenhum livro encontrado. Adicione livros pelas abas anteriores!")
        return

    # Summary metrics
    total = len(df)
    lidos = len(df[df["status_leitura"] == "Lido"])
    lendo = len(df[df["status_leitura"] == "Lendo"])
    quero = len(df[df["status_leitura"] == "Quero Ler"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Livros", total)
    m2.metric("Lidos", lidos)
    m3.metric("Lendo", lendo)
    m4.metric("Quero Ler", quero)

    st.divider()

    # Grid display — 4 cards per row
    cols_per_row = 4
    rows = [df.iloc[i:i+cols_per_row] for i in range(0, len(df), cols_per_row)]

    for chunk in rows:
        cols = st.columns(cols_per_row)
        for col, (_, row) in zip(cols, chunk.iterrows()):
            with col:
                render_library_card(row.to_dict())
        st.divider()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    init_db()

    st.title("📚 Minha Biblioteca Virtual")
    st.caption("Gerencie suas leituras no estilo Skoob/Goodreads")

    tab1, tab2, tab3 = st.tabs([
        "🔍 Buscar e Adicionar",
        "✏️ Cadastro Manual",
        "📚 Minha Biblioteca",
    ])

    with tab1:
        tab_buscar()
    with tab2:
        tab_manual()
    with tab3:
        tab_biblioteca()


if __name__ == "__main__":
    main()

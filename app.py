import streamlit as st
import pandas as pd
from ortools.sat.python import cp_model

st.set_page_config(page_title="Teste Simples", page_icon="🧪")

st.title("🧪 Teste de Ambiente - Escala HC15")
st.success("✅ Todas as bibliotecas (Streamlit, Pandas, OR-Tools) foram carregadas com sucesso!")

st.write("### Verificação de Dependências:")
st.write(f"- **Streamlit:** Versão `{st.__version__}`")
st.write(f"- **Pandas:** Versão `{pd.__version__}`")
st.write("- **Google OR-Tools (CP-SAT):** Módulo `cp_model` importado perfeitamente!")

if st.button("🚀 Testar Interatividade"):
    st.balloons()
    st.info("A aplicação respondeu ao clique! O ambiente está 100% funcional.")

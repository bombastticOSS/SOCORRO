"""
Protótipo de escala assistencial — HC 15º Andar

Execução:
    pip install -r requirements_escala_hc15_v6.txt
    streamlit run sistema_escala_hc15_v6.py

O arquivo persiste somente dados operacionais agregados no computador em que
está sendo executado. Não armazena prontuários, diagnósticos ou identificadores
de pacientes.
"""

from __future__ import annotations

import calendar
import io
import json
import os
import random
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from ortools.sat.python import cp_model

st.set_page_config(
    page_title="Escala Assistencial | HC 15º Andar",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, GridOptionsBuilder, JsCode

    AGGRID_DISPONIVEL = True
except ImportError:
    AGGRID_DISPONIVEL = False

    # Mantém o modo de contingência carregável quando a dependência opcional
    # ainda não foi instalada. Os objetos não são usados nesse modo.
    def JsCode(*_args: Any, **_kwargs: Any) -> None:  # type: ignore[misc]
        return None


# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DA COMPETÊNCIA E DAS REGRAS OPERACIONAIS
# -----------------------------------------------------------------------------
ANO = 2026
MES = 11
LEITOS_TOTAIS = 60
CODIGOS_EDITAVEIS = ["", "M6", "D12", "N12", "FP", "FE", "AT", "LM", "LIC"]
CODIGOS_VALIDOS = set(CODIGOS_EDITAVEIS)
CODIGOS_AFASTAMENTO = {"FE", "AT", "LM", "LIC"}
TURNOS = ("M6", "D12", "N12")
HORAS_POR_CODIGO = {"M6": 6, "D12": 12, "N12": 12}
NOMES_DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")

# Este é o único bloco a ajustar caso o dimensionamento mínimo do setor mude.
# As chaves são cargo curto -> turno -> número mínimo de profissionais.
REQUISITOS_COBERTURA = {
    "dia_util": {
        "ENF": {"M6": 1, "D12": 5, "N12": 4},
        "TÉC": {"M6": 1, "D12": 6, "N12": 3},
    },
    "fim_de_semana": {
        "ENF": {"M6": 1, "D12": 3, "N12": 4},
        "TÉC": {"M6": 1, "D12": 4, "N12": 3},
    },
}

COMPETENCIA = date(ANO, MES, 1)
NUM_DIAS = calendar.monthrange(ANO, MES)[1]
DATAS = [date(ANO, MES, dia) for dia in range(1, NUM_DIAS + 1)]
COLUNAS_DIAS = [f"D{data.day:02d}" for data in DATAS]
COLUNAS_FIM_DE_SEMANA = [f"D{data.day:02d}" for data in DATAS if data.weekday() >= 5]
ROTULOS_DIAS = {
    f"D{data.day:02d}": f"{data.day:02d}\n{NOMES_DIAS[data.weekday()]}" for data in DATAS
}


def caminho_dados() -> Path:
    """Usa diretório local explícito e cria-o; não engole falhas de persistência."""
    raiz_padrao = Path(os.getenv("LOCALAPPDATA", Path.home())) / "HC15_Escala"
    raiz = Path(os.getenv("ESCALA_DATA_DIR", str(raiz_padrao)))
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


ARQUIVO_ESTADO = caminho_dados() / f"escala_{ANO}_{MES:02d}_v6.json"


# -----------------------------------------------------------------------------
# BASE DEMONSTRATIVA — substitua esta fonte por integração segura no projeto real
# -----------------------------------------------------------------------------
@st.cache_data
def carregar_profissionais() -> pd.DataFrame:
    dados = """ID,Nome,Sexo,Cargo,Turno_Atribuido,Carga_Horaria_Semanal,Regime_12x36
ENF-01,Ana Paula Silva,Feminino,Enfermeiro,Diurno,36h,Não
ENF-02,Beatriz Oliveira,Feminino,Enfermeiro,Diurno,36h,Não
ENF-03,Carlos Eduardo Lima,Masculino,Enfermeiro,Diurno,40h,Não
ENF-04,Daniela Martins,Feminino,Enfermeiro,Diurno,36h,Não
ENF-05,Eduardo Rocha,Masculino,Enfermeiro,Diurno,40h,Não
ENF-06,Fernanda Alves,Feminino,Enfermeiro,Diurno,36h,Não
ENF-07,Gabriel Santos,Masculino,Enfermeiro,Diurno,40h,Não
ENF-08,Helena Costa,Feminino,Enfermeiro,Diurno,36h,Não
ENF-09,Igor Ribeiro,Masculino,Enfermeiro,Diurno,36h,Não
ENF-10,Juliana Lima,Feminino,Enfermeiro,Diurno,40h,Não
ENF-11,Kátia Mendes,Feminino,Enfermeiro,Diurno,36h,Não
ENF-12,Lucas Pereira,Masculino,Enfermeiro,Diurno,40h,Não
ENF-13,Marcelo Silva,Masculino,Enfermeiro,Noturno,36h,Sim
ENF-14,Nádia Ferreira,Feminino,Enfermeiro,Noturno,36h,Sim
ENF-15,Otávio Barbosa,Masculino,Enfermeiro,Noturno,40h,Sim
ENF-16,Patricia Gomes,Feminino,Enfermeiro,Noturno,36h,Sim
ENF-17,Renato Cardoso,Masculino,Enfermeiro,Noturno,36h,Sim
ENF-18,Simone Duarte,Feminino,Enfermeiro,Noturno,40h,Sim
ENF-19,Thiago Moraes,Masculino,Enfermeiro,Noturno,36h,Sim
ENF-20,Vanessa Costa,Feminino,Enfermeiro,Noturno,40h,Sim
TEC-01,Aline Souza,Feminino,Técnico de Enfermagem,Diurno,36h,Não
TEC-02,Bruno Carrijo,Masculino,Técnico de Enfermagem,Diurno,36h,Não
TEC-03,Camila Rodrigues,Feminino,Técnico de Enfermagem,Diurno,36h,Não
TEC-04,Diego Fernandes,Masculino,Técnico de Enfermagem,Diurno,40h,Não
TEC-05,Eliana Machado,Feminino,Técnico de Enfermagem,Diurno,40h,Não
TEC-06,Fábio Henrique,Masculino,Técnico de Enfermagem,Diurno,36h,Não
TEC-07,Gisele Prado,Feminino,Técnico de Enfermagem,Diurno,36h,Não
TEC-08,Heitor Vasconcelos,Masculino,Técnico de Enfermagem,Diurno,40h,Não
TEC-09,Isabela Faria,Feminino,Técnico de Enfermagem,Diurno,40h,Não
TEC-10,João Vitor Cruz,Masculino,Técnico de Enfermagem,Diurno,40h,Não
TEC-11,Karen Stephanie,Feminino,Técnico de Enfermagem,Diurno,36h,Não
TEC-12,Leonardo Nogueira,Masculino,Técnico de Enfermagem,Diurno,36h,Não
TEC-13,Mariana Freitas,Feminino,Técnico de Enfermagem,Diurno,40h,Não
TEC-14,Natália Guimarães,Feminino,Técnico de Enfermagem,Diurno,36h,Não
TEC-15,Orlando Ramos,Masculino,Técnico de Enfermagem,Noturno,36h,Sim
TEC-16,Paula Tejada,Feminino,Técnico de Enfermagem,Noturno,36h,Sim
TEC-17,Quintino Bocaiúva,Masculino,Técnico de Enfermagem,Noturno,36h,Sim
TEC-18,Raquel Xavier,Feminino,Técnico de Enfermagem,Noturno,36h,Sim
TEC-19,Samuel Rosa,Masculino,Técnico de Enfermagem,Noturno,36h,Sim
TEC-20,Tatiana Valente,Feminino,Técnico de Enfermagem,Noturno,40h,Sim"""
    profissionais = pd.read_csv(io.StringIO(dados))
    profissionais["Código/Cargo"] = profissionais.apply(
        lambda linha: f"{linha['ID']} · {'ENF' if linha['Cargo'] == 'Enfermeiro' else 'TÉC'}",
        axis=1,
    )
    profissionais["Cargo curto"] = profissionais["Cargo"].map(
        {"Enfermeiro": "ENF", "Técnico de Enfermagem": "TÉC"}
    )
    profissionais["Meta"] = profissionais["Carga_Horaria_Semanal"].map({"36h": 156, "40h": 176})
    return profissionais


PROFISSIONAIS = carregar_profissionais()
POR_ID = PROFISSIONAIS.set_index("ID").to_dict("index")


# -----------------------------------------------------------------------------
# ESTADO E PERSISTÊNCIA
# -----------------------------------------------------------------------------
def valor_normalizado(valor: Any) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip().upper()


def escala_vazia() -> pd.DataFrame:
    escala = PROFISSIONAIS[["ID"]].copy()
    for coluna in COLUNAS_DIAS:
        escala[coluna] = ""
    return escala


def censo_vazio() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Dia": [f"{data.day:02d} {NOMES_DIAS[data.weekday()]}" for data in DATAS],
            "Ala A": [0] * NUM_DIAS,
            "Ala B": [0] * NUM_DIAS,
        }
    )


def normalizar_escala_registros(registros: list[dict[str, Any]]) -> pd.DataFrame:
    recebida = pd.DataFrame(registros)
    base = escala_vazia().set_index("ID")
    if "ID" not in recebida.columns:
        return base.reset_index()
    recebida = recebida.set_index("ID")
    for identificador in base.index:
        if identificador not in recebida.index:
            continue
        for coluna in COLUNAS_DIAS:
            if coluna in recebida.columns:
                base.at[identificador, coluna] = valor_normalizado(recebida.at[identificador, coluna])
    return base.reset_index()


def normalizar_censo_registros(registros: list[dict[str, Any]]) -> pd.DataFrame:
    base = censo_vazio()
    recebida = pd.DataFrame(registros)
    for coluna in ("Ala A", "Ala B"):
        if coluna in recebida.columns:
            valores = pd.to_numeric(recebida[coluna], errors="coerce").fillna(0).clip(lower=0, upper=LEITOS_TOTAIS)
            base.loc[: min(len(base), len(valores)) - 1, coluna] = valores.iloc[: len(base)].astype(int).tolist()
    return base


def carregar_estado() -> dict[str, Any]:
    if not ARQUIVO_ESTADO.exists():
        return {}
    try:
        with ARQUIVO_ESTADO.open("r", encoding="utf-8") as arquivo:
            estado = json.load(arquivo)
    except (OSError, json.JSONDecodeError) as erro:
        st.warning(f"Não foi possível recuperar o estado local: {erro}")
        return {}
    return estado if isinstance(estado, dict) else {}


def preparar_estado() -> None:
    if "escala" in st.session_state:
        return
    estado = carregar_estado()
    st.session_state.escala = normalizar_escala_registros(estado.get("escala", []))
    st.session_state.censo = normalizar_censo_registros(estado.get("censo", []))
    st.session_state.travas = {
        str(identificador): set(dias)
        for identificador, dias in estado.get("travas", {}).items()
        if str(identificador) in POR_ID and isinstance(dias, list)
    }
    st.session_state.pedidos_folga = {
        str(identificador): set(dias)
        for identificador, dias in estado.get("pedidos_folga", {}).items()
        if str(identificador) in POR_ID and isinstance(dias, list)
    }
    st.session_state.ultima_otimizacao = estado.get("ultima_otimizacao", "Ainda não executada")


def salvar_estado() -> None:
    estado = {
        "versao": 6,
        "competencia": COMPETENCIA.isoformat(),
        "escala": st.session_state.escala.to_dict(orient="records"),
        "censo": st.session_state.censo.to_dict(orient="records"),
        "travas": {identificador: sorted(dias) for identificador, dias in st.session_state.travas.items() if dias},
        "pedidos_folga": {
            identificador: sorted(dias)
            for identificador, dias in st.session_state.pedidos_folga.items()
            if dias
        },
        "ultima_otimizacao": st.session_state.ultima_otimizacao,
    }
    try:
        with ARQUIVO_ESTADO.open("w", encoding="utf-8") as arquivo:
            json.dump(estado, arquivo, ensure_ascii=False, indent=2)
    except OSError as erro:
        st.error(f"Não foi possível salvar o estado local em {ARQUIVO_ESTADO}: {erro}")


preparar_estado()


# -----------------------------------------------------------------------------
# CÁLCULOS DE COBERTURA, AUDITORIA E DIMENSIONAMENTO
# -----------------------------------------------------------------------------
def eh_fim_de_semana(indice_dia: int) -> bool:
    return DATAS[indice_dia].weekday() >= 5


def requisito_do_dia(indice_dia: int) -> dict[str, dict[str, int]]:
    tipo = "fim_de_semana" if eh_fim_de_semana(indice_dia) else "dia_util"
    return REQUISITOS_COBERTURA[tipo]


def horas_de(valor: str) -> int:
    return HORAS_POR_CODIGO.get(valor_normalizado(valor), 0)


def turno_permitido(profissional: dict[str, Any], valor: str) -> bool:
    if valor not in TURNOS:
        return True
    if profissional["Turno_Atribuido"] == "Noturno":
        return valor == "N12"
    return valor in {"M6", "D12"}


def valor_exibido(identificador: str, coluna: str, valor_real: str) -> str:
    """FP é preferência, não uma folga obrigatória: só aparece quando não há plantão."""
    if not valor_real and coluna in st.session_state.pedidos_folga.get(identificador, set()):
        return "FP"
    return valor_real


def calcular_metricas_diarias(escala: pd.DataFrame) -> pd.DataFrame:
    linhas: list[dict[str, Any]] = []
    por_id = escala.set_index("ID")

    for indice, data in enumerate(DATAS):
        coluna = COLUNAS_DIAS[indice]
        exigido = requisito_do_dia(indice)
        contagem = {cargo: {turno: 0 for turno in TURNOS} for cargo in ("ENF", "TÉC")}
        horas = 0
        pessoas = 0

        for identificador, profissional in POR_ID.items():
            valor = valor_normalizado(por_id.at[identificador, coluna])
            if valor in TURNOS:
                contagem[profissional["Cargo curto"]][valor] += 1
                pessoas += 1
                horas += horas_de(valor)

        previstos = sum(exigido[cargo][turno] for cargo in exigido for turno in TURNOS)
        realizados = sum(contagem[cargo][turno] for cargo in contagem for turno in TURNOS)
        deficit = sum(
            max(0, exigido[cargo][turno] - contagem[cargo][turno])
            for cargo in exigido
            for turno in TURNOS
        )
        excedente = sum(
            max(0, contagem[cargo][turno] - exigido[cargo][turno])
            for cargo in exigido
            for turno in TURNOS
        )
        linhas.append(
            {
                "Chave": coluna,
                "Dia": f"{data.day:02d} {NOMES_DIAS[data.weekday()]}",
                "Tipo de dia": "Fim de semana" if eh_fim_de_semana(indice) else "Dia útil",
                "ENF M6": contagem["ENF"]["M6"],
                "ENF D12": contagem["ENF"]["D12"],
                "ENF N12": contagem["ENF"]["N12"],
                "TÉC M6": contagem["TÉC"]["M6"],
                "TÉC D12": contagem["TÉC"]["D12"],
                "TÉC N12": contagem["TÉC"]["N12"],
                "Pessoas escaladas": pessoas,
                "Plantões previstos": previstos,
                "Déficit": deficit,
                "Excedente": excedente,
                "Cobertura %": round(min(100, realizados / previstos * 100), 1) if previstos else 100.0,
                "Horas programadas": horas,
            }
        )
    return pd.DataFrame(linhas)


def auditar_escala(escala: pd.DataFrame) -> tuple[dict[str, set[str]], list[str], pd.DataFrame]:
    """Marca células problemáticas; não afirma conformidade legal integral."""
    problemas: dict[str, set[str]] = {identificador: set() for identificador in POR_ID}
    mensagens: list[str] = []
    por_id = escala.set_index("ID")

    for identificador, profissional in POR_ID.items():
        valores = [valor_normalizado(por_id.at[identificador, coluna]) for coluna in COLUNAS_DIAS]
        nome = profissional["Nome"]

        for indice, valor in enumerate(valores):
            if valor not in CODIGOS_VALIDOS:
                problemas[identificador].add(COLUNAS_DIAS[indice])
                mensagens.append(f"{nome}: código inválido “{valor}” no dia {indice + 1}.")
            elif not turno_permitido(profissional, valor):
                problemas[identificador].add(COLUNAS_DIAS[indice])
                mensagens.append(f"{nome}: {valor} é incompatível com o turno cadastrado no dia {indice + 1}.")

        for indice in range(NUM_DIAS - 1):
            atual, proximo = valores[indice], valores[indice + 1]
            if atual in {"D12", "N12"} and proximo in TURNOS:
                problemas[identificador].update({COLUNAS_DIAS[indice], COLUNAS_DIAS[indice + 1]})
                mensagens.append(
                    f"{nome}: intervalo insuficiente entre os dias {indice + 1} ({atual}) e {indice + 2} ({proximo})."
                )

        consecutivos = 0
        for indice, valor in enumerate(valores):
            consecutivos = consecutivos + 1 if valor in TURNOS else 0
            if consecutivos > 6:
                problemas[identificador].add(COLUNAS_DIAS[indice])
                mensagens.append(f"{nome}: mais de seis dias consecutivos de trabalho no dia {indice + 1}.")

        if profissional["Sexo"] == "Feminino":
            domingos = [indice for indice, data in enumerate(DATAS) if data.weekday() == 6]
            for anterior, seguinte in zip(domingos, domingos[1:]):
                if valores[anterior] in TURNOS and valores[seguinte] in TURNOS:
                    problemas[identificador].update({COLUNAS_DIAS[anterior], COLUNAS_DIAS[seguinte]})
                    mensagens.append(f"{nome}: domingos consecutivos escalados ({anterior + 1} e {seguinte + 1}).")

    metricas = calcular_metricas_diarias(escala)
    for _, linha in metricas.iterrows():
        if int(linha["Déficit"]) > 0:
            mensagens.append(f"Dia {linha['Dia']}: déficit de {int(linha['Déficit'])} posição(ões) na cobertura mínima.")
    return problemas, mensagens, metricas


def totais_por_profissional(escala: pd.DataFrame) -> pd.DataFrame:
    por_id = escala.set_index("ID")
    linhas = []
    for _, profissional in PROFISSIONAIS.iterrows():
        identificador = profissional["ID"]
        realizado = sum(horas_de(por_id.at[identificador, coluna]) for coluna in COLUNAS_DIAS)
        meta = int(profissional["Meta"])
        linhas.append({"ID": identificador, "Meta": meta, "Realizado": realizado, "Saldo": realizado - meta})
    return pd.DataFrame(linhas).set_index("ID")


def linha_cobertura(metricas: pd.DataFrame) -> dict[str, Any]:
    linha: dict[str, Any] = {
        "_tipo": "cobertura",
        "_id": "__COBERTURA__",
        "Código/Cargo": "STATUS",
        "Nome": "Cobertura mínima",
        "Meta": "",
        "Realizado": "",
        "Saldo": "",
        "_travas": "[]",
        "_problemas": "[]",
    }
    for _, metrica in metricas.iterrows():
        coluna = metrica["Chave"]
        deficit, excedente = int(metrica["Déficit"]), int(metrica["Excedente"])
        linha[coluna] = "OK" if deficit == 0 and excedente == 0 else (f"–{deficit}" if deficit else f"+{excedente}")
    return linha


def montar_grade_exibicao(escala: pd.DataFrame) -> pd.DataFrame:
    problemas, _, metricas = auditar_escala(escala)
    totais = totais_por_profissional(escala)
    por_id = escala.set_index("ID")
    linhas: list[dict[str, Any]] = [linha_cobertura(metricas)]

    for cargo, titulo in (("ENF", None), ("TÉC", "TÉCNICOS DE ENFERMAGEM")):
        if titulo:
            divisor = {
                "_tipo": "divisor",
                "_id": "__TECNICOS__",
                "Código/Cargo": "EQUIPE",
                "Nome": titulo,
                "Meta": "",
                "Realizado": "",
                "Saldo": "",
                "_travas": "[]",
                "_problemas": "[]",
            }
            divisor.update({coluna: "" for coluna in COLUNAS_DIAS})
            linhas.append(divisor)

            # Repetir as datas elimina a necessidade de subir até o topo para
            # conferir o dia ao lançar a escala dos técnicos.
            cabecalho_tecnicos = {
                "_tipo": "cabecalho_tecnicos",
                "_id": "__DATAS_TECNICOS__",
                "Código/Cargo": "DATAS",
                "Nome": "Técnicos de enfermagem",
                "Meta": "",
                "Realizado": "",
                "Saldo": "",
                "_travas": "[]",
                "_problemas": "[]",
            }
            cabecalho_tecnicos.update(
                {coluna: ROTULOS_DIAS[coluna].replace("\n", " ") for coluna in COLUNAS_DIAS}
            )
            linhas.append(cabecalho_tecnicos)

        for _, profissional in PROFISSIONAIS[PROFISSIONAIS["Cargo curto"] == cargo].iterrows():
            identificador = profissional["ID"]
            linha = {
                "_tipo": "profissional",
                "_id": identificador,
                "Código/Cargo": profissional["Código/Cargo"],
                "Nome": profissional["Nome"],
                "Meta": f"{int(totais.at[identificador, 'Meta'])}h",
                "Realizado": f"{int(totais.at[identificador, 'Realizado'])}h",
                "Saldo": f"{int(totais.at[identificador, 'Saldo']):+d}h",
                # A grade recebe strings JSON, não listas Python: assim o
                # JavaScript não tenta chamar .includes em um objeto serializado.
                "_travas": json.dumps(sorted(st.session_state.travas.get(identificador, set()))),
                "_problemas": json.dumps(sorted(problemas.get(identificador, set()))),
            }
            for coluna in COLUNAS_DIAS:
                linha[coluna] = valor_exibido(identificador, coluna, valor_normalizado(por_id.at[identificador, coluna]))
            linhas.append(linha)
    return pd.DataFrame(linhas)


# -----------------------------------------------------------------------------
# ATUALIZAÇÃO MANUAL, TRAVAS E PEDIDOS DE FOLGA
# -----------------------------------------------------------------------------
def aplicar_edicoes_da_grade(retorno: pd.DataFrame) -> bool:
    """Registra edição manual e trava a célula; FP permanece uma preferência flexível."""
    if retorno is None or retorno.empty or "_id" not in retorno.columns:
        return False
    anterior = montar_grade_exibicao(st.session_state.escala).set_index("_id")
    escala = st.session_state.escala.set_index("ID")
    alterou = False

    for _, linha in retorno.iterrows():
        identificador = str(linha.get("_id", ""))
        if identificador not in POR_ID or identificador not in anterior.index:
            continue
        for coluna in COLUNAS_DIAS:
            novo = valor_normalizado(linha.get(coluna, ""))
            antigo_exibido = valor_normalizado(anterior.at[identificador, coluna])
            if novo == antigo_exibido:
                continue
            alterou = True
            pedidos = st.session_state.pedidos_folga.setdefault(identificador, set())
            travas = st.session_state.travas.setdefault(identificador, set())

            if novo == "FP":
                escala.at[identificador, coluna] = ""
                pedidos.add(coluna)
                travas.discard(coluna)
            else:
                escala.at[identificador, coluna] = novo
                pedidos.discard(coluna)
                # Inclui branco: o gestor pode proteger explicitamente uma folga.
                travas.add(coluna)

    if alterou:
        st.session_state.escala = escala.reset_index()
        salvar_estado()
    return alterou


def aplicar_marcacao_em_lote(identificadores: list[str], dias: list[str], codigo: str) -> int:
    escala = st.session_state.escala.set_index("ID")
    modificadas = 0
    for identificador in identificadores:
        travas = st.session_state.travas.setdefault(identificador, set())
        pedidos = st.session_state.pedidos_folga.setdefault(identificador, set())
        for coluna in dias:
            if coluna in travas:
                continue
            if codigo == "FP":
                escala.at[identificador, coluna] = ""
                pedidos.add(coluna)
            else:
                escala.at[identificador, coluna] = codigo
                pedidos.discard(coluna)
                travas.add(coluna)
            modificadas += 1
    st.session_state.escala = escala.reset_index()
    salvar_estado()
    return modificadas


def aplicar_travas(identificador: str, dias: list[str], acao: str) -> None:
    travas = st.session_state.travas.setdefault(identificador, set())
    if acao == "travar":
        travas.update(dias)
    else:
        travas.difference_update(dias)
    # Força a atualização das regras de edição da grade após destravar.
    st.session_state.revisao_grade = st.session_state.get("revisao_grade", 0) + 1
    salvar_estado()


def carregar_pedidos_arquivo(arquivo: Any) -> tuple[int, list[str]]:
    """Lê Nome/ID e Dias_Folga/Dias, mantendo pedido como restrição suave."""
    if arquivo.name.lower().endswith(".xlsx"):
        pedidos = pd.read_excel(arquivo)
    else:
        pedidos = pd.read_csv(arquivo)
    avisos: list[str] = []
    incluidos = 0
    for _, linha in pedidos.iterrows():
        referencia = str(linha.get("ID", linha.get("Nome", linha.get("Nome Completo", "")))).strip().lower()
        dias_brutos = str(linha.get("Dias_Folga", linha.get("Dias", "")))
        identificador = next(
            (
                ident
                for ident, prof in POR_ID.items()
                if referencia == ident.lower() or referencia == str(prof["Nome"]).lower()
            ),
            None,
        )
        if not identificador:
            avisos.append(f"Colaborador não localizado: {referencia or 'sem identificação'}.")
            continue
        for parte in dias_brutos.split(","):
            texto = parte.strip().lower().replace("dia", "").replace("d", "").strip()
            if not texto.isdigit() or not 1 <= int(texto) <= NUM_DIAS:
                continue
            st.session_state.pedidos_folga.setdefault(identificador, set()).add(f"D{int(texto):02d}")
            incluidos += 1
    salvar_estado()
    return incluidos, avisos


# -----------------------------------------------------------------------------
# OTIMIZADOR CP-SAT: respeita toda célula travada, inclusive folga vazia
# -----------------------------------------------------------------------------
def executar_otimizacao() -> tuple[bool, str]:
    escala_atual = st.session_state.escala.set_index("ID")
    modelo = cp_model.CpModel()
    profissionais = list(POR_ID)
    variaveis = {
        (identificador, indice, turno): modelo.NewBoolVar(f"{identificador}_{indice}_{turno}")
        for identificador in profissionais
        for indice in range(NUM_DIAS)
        for turno in TURNOS
    }

    # Domínio de cada pessoa/dia e aplicação das travas do gestor.
    for identificador in profissionais:
        profissional = POR_ID[identificador]
        for indice, coluna in enumerate(COLUNAS_DIAS):
            modelo.AddAtMostOne(variaveis[identificador, indice, turno] for turno in TURNOS)
            valor = valor_normalizado(escala_atual.at[identificador, coluna])
            travada = coluna in st.session_state.travas.get(identificador, set())
            if travada:
                if valor in TURNOS:
                    for turno in TURNOS:
                        modelo.Add(variaveis[identificador, indice, turno] == int(turno == valor))
                else:
                    for turno in TURNOS:
                        modelo.Add(variaveis[identificador, indice, turno] == 0)
            elif profissional["Turno_Atribuido"] == "Noturno":
                modelo.Add(variaveis[identificador, indice, "M6"] == 0)
                modelo.Add(variaveis[identificador, indice, "D12"] == 0)
            else:
                modelo.Add(variaveis[identificador, indice, "N12"] == 0)

    # Descanso entre jornadas, máximo de seis dias seguidos e domingos.
    for identificador in profissionais:
        profissional = POR_ID[identificador]
        for indice in range(NUM_DIAS - 1):
            doze_horas = variaveis[identificador, indice, "D12"] + variaveis[identificador, indice, "N12"]
            proximo_dia = sum(variaveis[identificador, indice + 1, turno] for turno in TURNOS)
            modelo.Add(doze_horas + proximo_dia <= 1)
        for inicio in range(NUM_DIAS - 6):
            modelo.Add(
                sum(variaveis[identificador, inicio + deslocamento, turno] for deslocamento in range(7) for turno in TURNOS)
                <= 6
            )
        if profissional["Sexo"] == "Feminino":
            domingos = [indice for indice, data in enumerate(DATAS) if data.weekday() == 6]
            for anterior, seguinte in zip(domingos, domingos[1:]):
                modelo.Add(
                    sum(variaveis[identificador, anterior, turno] for turno in TURNOS)
                    + sum(variaveis[identificador, seguinte, turno] for turno in TURNOS)
                    <= 1
                )

    # Cobertura mínima por categoria e turno.
    for indice in range(NUM_DIAS):
        requisito = requisito_do_dia(indice)
        for cargo in ("ENF", "TÉC"):
            ids_cargo = [ident for ident in profissionais if POR_ID[ident]["Cargo curto"] == cargo]
            for turno in TURNOS:
                modelo.Add(sum(variaveis[ident, indice, turno] for ident in ids_cargo) == requisito[cargo][turno])

    # A cada execução, desempates recebem um peso novo. As travas permanecem
    # absolutas; somente as células livres podem gerar uma alternativa distinta.
    semente = random.SystemRandom().randint(1, 2_147_483_647)
    sorteio = random.Random(semente)
    penalidades = []
    desvios_absolutos = []
    for identificador in profissionais:
        meta = int(POR_ID[identificador]["Meta"])
        horas = sum(
            variaveis[identificador, indice, "M6"] * 6
            + variaveis[identificador, indice, "D12"] * 12
            + variaveis[identificador, indice, "N12"] * 12
            for indice in range(NUM_DIAS)
        )
        diferenca = modelo.NewIntVar(-96, 96, f"diferenca_{identificador}")
        absoluto = modelo.NewIntVar(0, 96, f"absoluto_{identificador}")
        modelo.Add(diferenca == horas - meta)
        modelo.AddAbsEquality(absoluto, diferenca)
        desvios_absolutos.append(absoluto)
        # Primeiro equilibra o maior desvio individual; depois a soma dos saldos.
        # Isso evita concentrar dívidas grandes em poucas pessoas.
        penalidades.append(absoluto * 1_000)
        for coluna in st.session_state.pedidos_folga.get(identificador, set()):
            if coluna in COLUNAS_DIAS:
                indice = COLUNAS_DIAS.index(coluna)
                penalidades.append(sum(variaveis[identificador, indice, turno] for turno in TURNOS) * 100_000)

    maior_desvio = modelo.NewIntVar(0, 96, "maior_desvio_individual")
    for desvio in desvios_absolutos:
        modelo.Add(maior_desvio >= desvio)
    penalidades.append(maior_desvio * 100_000)

    # Desempate de baixa prioridade: reorganiza os grupos sem sacrificar
    # cobertura, pedidos de folga ou equilíbrio de horas.
    for variavel in variaveis.values():
        penalidades.append(variavel * sorteio.randint(0, 9))

    modelo.Minimize(sum(penalidades))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = semente
    solver.parameters.randomize_search = True
    status = solver.Solve(modelo)

    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        descricao = "inviável" if status == cp_model.INFEASIBLE else "sem solução no tempo disponível"
        return False, (
            f"Otimização {descricao}. Revise as travas, afastamentos e a cobertura mínima; "
            "nenhuma escala existente foi alterada."
        )

    nova = escala_atual.copy()
    for identificador in profissionais:
        for indice, coluna in enumerate(COLUNAS_DIAS):
            if coluna in st.session_state.travas.get(identificador, set()):
                continue
            novo_valor = ""
            for turno in TURNOS:
                if solver.Value(variaveis[identificador, indice, turno]):
                    novo_valor = turno
                    break
            nova.at[identificador, coluna] = novo_valor

	st.session_state.escala = nova.reset_index()
    	st.session_state.ultima_otimizacao = "Concluída agora"
    	st.session_state.revisao_grade = st.session_state.get("revisao_grade", 0) + 1
    	salvar_estado()
    
   	qualidade = "ótima" if status == cp_model.OPTIMAL else "viável"
    	total_travas = sum(map(len, st.session_state.travas.values()))
    
   	return True, f"Escala {qualidade} gerada. Todas as {total_travas} travas foram preservadas."

# -----------------------------------------------------------------------------
# GRADE MENSAL: editável, com seleção, destaque e bloqueio por célula
# -----------------------------------------------------------------------------
ESTILO_CELULA = JsCode(
    """
function(params) {
  const field = params.colDef.field;
  const fimDeSemana = """
    + json.dumps(COLUNAS_FIM_DE_SEMANA)
    + """;
  const listaSegura = (raw) => {
    if (Array.isArray(raw)) return raw;
    if (typeof raw === 'string') { try { const parsed = JSON.parse(raw); return Array.isArray(parsed) ? parsed : []; } catch (_) { return []; } }
    return [];
  };
  const type = params.data._tipo;
  const value = String(params.value || '').toUpperCase();
  const locked = listaSegura(params.data._travas).includes(field);
  const issue = listaSegura(params.data._problemas).includes(field);
  let style = {textAlign: 'center', fontWeight: '600', paddingLeft: '2px', paddingRight: '2px'};
  if (type === 'divisor') return {backgroundColor: '#0f172a', color: '#f8fafc', fontWeight: '800'};
  if (type === 'cabecalho_tecnicos') return {backgroundColor: '#dbe4ee', color: '#0f172a', fontWeight: '800', textAlign: 'center'};
  if (type === 'cobertura') {
    if (value === 'OK') return {...style, backgroundColor: '#d1fae5', color: '#065f46'};
    if (value.startsWith('–')) return {...style, backgroundColor: '#fee2e2', color: '#991b1b', border: '2px solid #ef4444'};
    return {...style, backgroundColor: '#fef3c7', color: '#92400e'};
  }
  const colors = {
    'M6': ['#dbeafe', '#1e3a8a'], 'D12': ['#cffafe', '#155e75'], 'N12': ['#e0e7ff', '#3730a3'],
    'FP': ['#dcfce7', '#166534'], 'FE': ['#fef3c7', '#92400e'], 'AT': ['#fee2e2', '#991b1b'],
    'LM': ['#f3e8ff', '#6b21a8'], 'LIC': ['#ffedd5', '#9a3412']
  };
  // Fim de semana usa cinza-azulado e borda grafite; M6 continua azul.
  if (fimDeSemana.includes(field)) style.borderTop = '3px solid #64748b';
  if (colors[value]) { style.backgroundColor = colors[value][0]; style.color = colors[value][1]; }
  if (!value && field.startsWith('D')) style.backgroundColor = fimDeSemana.includes(field) ? '#f1f5f9' : '#ffffff';
  if (issue) { style.backgroundColor = '#fecaca'; style.color = '#991b1b'; style.border = '2px solid #dc2626'; }
  if (locked) { style.boxShadow = 'inset 0 0 0 2px #3730a3'; }
  return style;
}
"""
)

EDITAVEL_SE_NAO_TRAVADO = JsCode(
    """
function(params) {
  let travas = [];
  try { travas = Array.isArray(params.data._travas) ? params.data._travas : JSON.parse(params.data._travas || '[]'); } catch (_) { travas = []; }
  return params.data._tipo === 'profissional' && !travas.includes(params.colDef.field);
}
"""
)

RENDERIZAR_COM_CADEADO = JsCode(
    """
function(params) {
  let travas = [];
  try { travas = Array.isArray(params.data._travas) ? params.data._travas : JSON.parse(params.data._travas || '[]'); } catch (_) { travas = []; }
  const valor = params.value == null ? '' : String(params.value);
  // O componente Streamlit-AgGrid é renderizado por React e aceita texto,
  // não um HTMLElement criado manualmente.
  return travas.includes(params.colDef.field) ? valor + ' 🔒' : valor;
}
"""
)


def exibir_grade_mensal() -> None:
    grade = montar_grade_exibicao(st.session_state.escala)
    instrucao, legenda = st.columns([3.7, 2.3], vertical_alignment="center")
    with instrucao:
        st.caption(
            "Edite células livres pelo menu. A alteração manual recebe 🔒 automaticamente; "
            "FP é preferência e não bloqueia a otimização. Use o painel de travas para liberar uma célula."
        )
    with legenda:
        st.markdown(
            "<div class='legenda'>"
            "<span class='m6'>M6</span><span class='d12'>D12</span><span class='n12'>N12</span><span class='fp'>FP</span>"
            "<span class='fe'>FE</span><span class='at'>AT</span><span class='lm'>LM</span><span class='lic'>LIC</span>"
            "<span class='lock'>🔒</span><span class='error'>conflito</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    if not AGGRID_DISPONIVEL:
        st.warning("Para a grade colorida e os cadeados por célula, instale as dependências indicadas no arquivo requirements.")
        opcoes_coluna = {
            coluna: st.column_config.SelectboxColumn(ROTULOS_DIAS[coluna], options=CODIGOS_EDITAVEIS, width="small")
            for coluna in COLUNAS_DIAS
        }
        simples = grade[grade["_tipo"] == "profissional"].copy()
        retorno = st.data_editor(
            simples,
            hide_index=True,
            width="stretch",
            disabled=["_tipo", "_id", "Código/Cargo", "Nome", "Meta", "Realizado", "Saldo", "_travas", "_problemas"],
            column_config=opcoes_coluna,
            key="grade_basica",
        )
        aplicar_edicoes_da_grade(retorno)
        return

    construtor = GridOptionsBuilder.from_dataframe(grade)
    construtor.configure_default_column(sortable=False, filter=False, resizable=False, suppressMovable=True)
    construtor.configure_column("_tipo", hide=True)
    construtor.configure_column("_id", hide=True)
    construtor.configure_column("_travas", hide=True)
    construtor.configure_column("_problemas", hide=True)
    construtor.configure_column("Código/Cargo", width=104, minWidth=94, maxWidth=120, editable=False, cellStyle=ESTILO_CELULA)
    construtor.configure_column("Nome", width=165, minWidth=140, editable=False, cellStyle=ESTILO_CELULA)
    for coluna in COLUNAS_DIAS:
        construtor.configure_column(
            coluna,
            header_name=ROTULOS_DIAS[coluna],
            width=31,
            minWidth=27,
            maxWidth=42,
            editable=EDITAVEL_SE_NAO_TRAVADO,
            cellEditor="agSelectCellEditor",
            cellEditorParams={"values": CODIGOS_EDITAVEIS},
            cellStyle=ESTILO_CELULA,
            cellRenderer=RENDERIZAR_COM_CADEADO,
            wrapHeaderText=True,
        )
    for coluna in ("Meta", "Realizado", "Saldo"):
        construtor.configure_column(coluna, width=70, minWidth=62, editable=False, cellStyle=ESTILO_CELULA)
    construtor.configure_grid_options(
        headerHeight=48,
        rowHeight=34,
        suppressHorizontalScroll=True,
        alwaysShowHorizontalScroll=False,
        stopEditingWhenCellsLoseFocus=True,
        suppressCellFocus=False,
    )
    opcoes = construtor.build()
    # Em monitores hospitalares usuais, mantém os 30 dias visíveis; em telas muito estreitas,
    # o navegador reduzirá as colunas até o mínimo, sem criar uma segunda visão semanal.
    # Cabeçalhos ficam visíveis enquanto a equipe técnica é percorrida.
    altura = min(max(610, len(grade) * 34 + 65), 940)
    resposta = AgGrid(
        grade,
        gridOptions=opcoes,
        height=altura,
        theme="streamlit",
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=True,
        reload_data=True,
        allow_unsafe_jscode=True,
        key="grade_mensal_hc15",
    )
    retorno = resposta.get("data") if isinstance(resposta, dict) else None
    if retorno is not None:
        retorno_df = retorno if isinstance(retorno, pd.DataFrame) else pd.DataFrame(retorno)
        if aplicar_edicoes_da_grade(retorno_df):
            st.rerun()


# -----------------------------------------------------------------------------
# DASHBOARD E CENSO MANUAL DAS ALAS
# -----------------------------------------------------------------------------
def atualizar_censo(censo_editado: pd.DataFrame) -> tuple[bool, list[str]]:
    proximo = censo_vazio()
    for coluna in ("Ala A", "Ala B"):
        proximo[coluna] = pd.to_numeric(censo_editado[coluna], errors="coerce").fillna(0).round().astype(int).clip(lower=0)
    invalidos = proximo[proximo["Ala A"] + proximo["Ala B"] > LEITOS_TOTAIS]
    if not invalidos.empty:
        dias = ", ".join(invalidos["Dia"].tolist())
        return False, [f"O total das alas A e B ultrapassa {LEITOS_TOTAIS} leitos em: {dias}."]
    if not proximo.equals(st.session_state.censo):
        st.session_state.censo = proximo
        salvar_estado()
    return True, []


def dashboard() -> None:
    _, mensagens, metricas = auditar_escala(st.session_state.escala)
    censo = st.session_state.censo.copy()
    censo["Total"] = censo["Ala A"] + censo["Ala B"]
    censo["Ocupação %"] = (censo["Total"] / LEITOS_TOTAIS * 100).round(1)
    resumo = metricas.copy()
    resumo["Pacientes Ala A"] = censo["Ala A"].values
    resumo["Pacientes Ala B"] = censo["Ala B"].values
    resumo["Pacientes"] = censo["Total"].values
    resumo["Ocupação %"] = censo["Ocupação %"].values
    resumo["Pacientes por profissional"] = resumo.apply(
        lambda linha: round(linha["Pacientes"] / linha["Pessoas escaladas"], 2) if linha["Pessoas escaladas"] else None,
        axis=1,
    )

    st.subheader("Censo manual e capacidade das alas")
    st.caption("Registre o censo de cada dia. Ala A + Ala B não pode ultrapassar 60 leitos; o censo não altera a escala automaticamente.")
    censo_para_editar = censo[["Dia", "Ala A", "Ala B", "Total", "Ocupação %"]]
    censo_coluna, capacidade_coluna = st.columns([1.45, 1], vertical_alignment="top")
    with censo_coluna:
        censo_editado = st.data_editor(
            censo_para_editar,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            disabled=["Dia", "Total", "Ocupação %"],
            column_config={
                "Ala A": st.column_config.NumberColumn("Ala A", min_value=0, max_value=LEITOS_TOTAIS, step=1, format="%d"),
                "Ala B": st.column_config.NumberColumn("Ala B", min_value=0, max_value=LEITOS_TOTAIS, step=1, format="%d"),
                "Ocupação %": st.column_config.NumberColumn("Ocupação %", format="%.1f%%"),
            },
            key="censo_alas",
        )
    with capacidade_coluna:
        st.markdown("##### Capacidade do 15º andar")
        k_a, k_b = st.columns(2)
        k_a.metric("Leitos", LEITOS_TOTAIS)
        k_b.metric("Maior ocupação", f"{float(censo['Ocupação %'].max()):.1f}%")
        st.info("O censo é uma informação de dimensionamento: ele contextualiza a escala, mas não cria plantões automaticamente.")
    valido, avisos = atualizar_censo(censo_editado)
    if not valido:
        for aviso in avisos:
            st.error(aviso)
        return
    if not censo_editado.equals(censo_para_editar):
        st.rerun()

    total_metas = int(totais_por_profissional(st.session_state.escala)["Meta"].sum())
    total_horas = int(resumo["Horas programadas"].sum())
    media_cobertura = float(resumo["Cobertura %"].mean())
    dias_criticos = int((resumo["Déficit"] > 0).sum())
    maior_ocupacao = float(resumo["Ocupação %"].max())
    media_pacientes = float(resumo["Pacientes"].mean())

    st.subheader("Leitura executiva da competência")
    k1, k2, k3 = st.columns(3)
    k1.metric("Cobertura média", f"{media_cobertura:.1f}%")
    k2.metric("Dias críticos", f"{dias_criticos}", "com déficit" if dias_criticos else "sem déficit")
    k3.metric("Horas programadas", f"{total_horas}h", f"meta total: {total_metas}h")
    k4, k5, k6 = st.columns(3)
    k4.metric("Ocupação máxima", f"{maior_ocupacao:.1f}%")
    k5.metric("Média de pacientes/dia", f"{media_pacientes:.1f}")
    k6.metric("Alertas de regra", len(mensagens))

    grafico = resumo.set_index("Dia")
    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("##### Pessoas escaladas × plantões previstos")
        st.bar_chart(grafico[["Pessoas escaladas", "Plantões previstos"]], width="stretch")
    with direita:
        st.markdown("##### Cobertura e ocupação")
        st.line_chart(grafico[["Cobertura %", "Ocupação %"]], width="stretch")

    comparativo = (
        resumo.groupby("Tipo de dia", as_index=False)
        .agg(
            **{
                "Cobertura média %": ("Cobertura %", "mean"),
                "Pessoas/dia": ("Pessoas escaladas", "mean"),
                "Horas/dia": ("Horas programadas", "mean"),
                "Pacientes/dia": ("Pacientes", "mean"),
                "Pacientes/profissional": ("Pacientes por profissional", "mean"),
                "Déficit acumulado": ("Déficit", "sum"),
            }
        )
        .round(2)
    )
    comparacao_coluna, criterio_coluna = st.columns([1.6, 1], vertical_alignment="top")
    with comparacao_coluna:
        st.markdown("##### Comparativo: dias úteis × fins de semana")
        st.dataframe(comparativo, width="stretch", hide_index=True)
    with criterio_coluna:
        st.markdown("##### Leitura rápida")
        st.caption("Cobertura mede plantões realizados contra o mínimo configurado. Pacientes por profissional é um indicador de carga, não substitui parâmetro assistencial oficial.")

    criticos = resumo[(resumo["Déficit"] > 0) | (resumo["Ocupação %"] >= 90)].copy()
    if not criticos.empty:
        atencao_coluna, espaco_coluna = st.columns([1.7, 1], vertical_alignment="top")
        with atencao_coluna:
            st.markdown("##### Dias que exigem atenção")
            st.dataframe(
                criticos[
                    ["Dia", "Pacientes Ala A", "Pacientes Ala B", "Ocupação %", "Pessoas escaladas", "Déficit", "Cobertura %"]
                ],
                width="stretch",
                hide_index=True,
            )
        with espaco_coluna:
            st.warning("Priorize dias com déficit. Acima de 90% de ocupação, reavalie a distribuição entre as alas.")
    else:
        st.success("Não há déficit de cobertura nem ocupação acima de 90% nos dados atuais.")

    with st.expander("Ver base diária completa de dimensionamento"):
        st.dataframe(
            resumo.drop(columns=["Chave"]),
            width="stretch",
            hide_index=True,
            height=520,
        )


def gerar_excel() -> bytes:
    _, _, metricas = auditar_escala(st.session_state.escala)
    grade = montar_grade_exibicao(st.session_state.escala)
    censo = st.session_state.censo.copy()
    censo["Total"] = censo["Ala A"] + censo["Ala B"]
    censo["Ocupação %"] = (censo["Total"] / LEITOS_TOTAIS * 100).round(1)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        grade.drop(columns=["_tipo", "_id", "_travas", "_problemas"]).to_excel(writer, sheet_name="Escala mensal", index=False)
        metricas.drop(columns=["Chave"]).to_excel(writer, sheet_name="Cobertura diária", index=False)
        censo.to_excel(writer, sheet_name="Censo alas", index=False)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# INTERFACE
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
  .block-container {max-width: 1600px; padding: 1.45rem 2.5rem 2.8rem; margin: 0 auto;}
  h1 {font-size: 1.7rem !important; margin-bottom: .1rem !important;}
  [data-testid="stMetric"] {background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: .65rem;}
  [data-testid="stMetricLabel"] {font-size: .78rem !important;}
  [data-testid="stMetricValue"] {font-size: 1.35rem !important;}
  .legenda {display:flex; flex-wrap:wrap; justify-content:flex-end; gap:.25rem; margin:.1rem 0 .35rem;}
  .legenda span {border-radius:999px; padding:.15rem .38rem; font-size:.64rem; font-weight:700;}
  .m6 {background:#dbeafe;color:#1e3a8a}.d12 {background:#cffafe;color:#155e75}.n12 {background:#e0e7ff;color:#3730a3}
  .fp {background:#dcfce7;color:#166534}.fe {background:#fef3c7;color:#92400e}.at {background:#fee2e2;color:#991b1b}
  .lm {background:#f3e8ff;color:#6b21a8}.lic {background:#ffedd5;color:#9a3412}.lock {background:#eef2ff;color:#3730a3}.error {background:#fecaca;color:#991b1b}
  .stTabs [data-baseweb="tab-list"] {gap: .55rem;}
  .stTabs [data-baseweb="tab"] {height: 42px; border-radius: 8px 8px 0 0; padding: 0 1.1rem;}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🏥 Escala Assistencial — HC 15º Andar")
st.caption(
    f"{COMPETENCIA.strftime('%B').capitalize()}/{ANO} · visão mensal editável · "
    "dimensionamento por cobertura e censo das alas A/B"
)

_, avisos_auditoria, metricas_atuais = auditar_escala(st.session_state.escala)
travas_ativas = sum(len(dias) for dias in st.session_state.travas.values())
c1, c2, c3, c4 = st.columns([1.15, 1.15, 1.2, 2.5])
with c1:
    if st.button("✨ Gerar nova alternativa", type="primary", width="stretch"):
        with st.spinner("Calculando a melhor escala sem modificar células protegidas..."):
            sucesso, mensagem = executar_otimizacao()
        if sucesso:
            st.success(mensagem)
            st.rerun()
        else:
            st.error(mensagem)
with c2:
    st.metric("Células protegidas", travas_ativas)
with c3:
    st.metric("Dias com déficit", int((metricas_atuais["Déficit"] > 0).sum()))
with c4:
    st.caption("A otimização respeita todas as células com 🔒. Para alterar uma delas, destrave-a explicitamente antes de editar.")

with st.expander("Ferramentas de gestão da escala", expanded=travas_ativas > 0):
    aba_travas, aba_lote, aba_pedidos, aba_exportar = st.tabs(["🔒 Travas", "📌 Lançamento em lote", "🌿 Pedidos de folga", "⬇️ Exportar"])
    with aba_travas:
        opcoes_pessoas = {f"{linha['Nome']} ({linha['Código/Cargo']})": linha["ID"] for _, linha in PROFISSIONAIS.iterrows()}
        esquerda, centro, direita = st.columns([2, 4, 4])
        pessoa_nome = esquerda.selectbox("Colaborador", list(opcoes_pessoas), key="trava_pessoa")
        identificador_trava = opcoes_pessoas[pessoa_nome]
        travas_da_pessoa = sorted(st.session_state.travas.get(identificador_trava, set()))
        esquerda.caption(f"{len(travas_da_pessoa)} dia(s) protegido(s)")
        dias_trava = centro.multiselect(
            "Dias protegidos / a gerir",
            COLUNAS_DIAS,
            format_func=lambda chave: ROTULOS_DIAS[chave].replace("\n", " "),
            default=travas_da_pessoa,
            key=f"trava_dias_{identificador_trava}",
        )
        with direita:
            b_travar, b_destravar, b_todos = st.columns(3)
            botao_travar = b_travar.button("🔒 Travar", width="stretch", key="botao_travar")
            botao_destravar = b_destravar.button("🔓 Seleção", width="stretch", key="botao_destravar")
            botao_destravar_todos = b_todos.button(
                "Liberar tudo", width="stretch", key="botao_destravar_todos", disabled=not travas_da_pessoa
            )
        if botao_travar and dias_trava:
            aplicar_travas(identificador_trava, dias_trava, "travar")
            st.success("Travas aplicadas.")
            st.rerun()
        if botao_destravar and dias_trava:
            aplicar_travas(identificador_trava, dias_trava, "destravar")
            st.success("Travas removidas.")
            st.rerun()
        if botao_destravar_todos:
            aplicar_travas(identificador_trava, travas_da_pessoa, "destravar")
            st.success("Todas as travas deste colaborador foram removidas.")
            st.rerun()
    with aba_lote:
        l1, l2, l3 = st.columns([3, 3, 2])
        selecionados = l1.multiselect("Colaboradores", list(opcoes_pessoas), key="lote_pessoas")
        codigo_lote = l2.selectbox("Código", CODIGOS_EDITAVEIS, format_func=lambda v: v or "FOL · folga regulamentar", key="lote_codigo")
        dias_lote = l3.multiselect("Dias", COLUNAS_DIAS, format_func=lambda chave: ROTULOS_DIAS[chave].replace("\n", " "), key="lote_dias")
        if st.button("Aplicar apenas em células livres", key="aplicar_lote"):
            ids = [opcoes_pessoas[nome] for nome in selecionados]
            if not ids or not dias_lote:
                st.warning("Selecione ao menos um colaborador e um dia.")
            else:
                numero = aplicar_marcacao_em_lote(ids, dias_lote, codigo_lote)
                st.success(f"{numero} célula(s) atualizada(s). Células já protegidas foram preservadas.")
                st.rerun()
    with aba_pedidos:
        arquivo_pedidos = st.file_uploader("Importar pedidos CSV ou XLSX", type=["csv", "xlsx"], key="pedidos_upload")
        st.caption("Colunas aceitas: ID ou Nome; Dias_Folga ou Dias. Exemplo: ENF-01 / 5, 12, 22.")
        if arquivo_pedidos is not None and st.button("Ler pedidos", key="ler_pedidos"):
            try:
                quantidade, avisos = carregar_pedidos_arquivo(arquivo_pedidos)
                st.success(f"{quantidade} pedido(s) de folga carregado(s) como preferência.")
                for aviso in avisos[:5]:
                    st.warning(aviso)
                st.rerun()
            except Exception as erro:
                st.error(f"Não foi possível ler o arquivo: {erro}")
    with aba_exportar:
        st.download_button(
            "Baixar Excel da escala e do dashboard",
            data=gerar_excel(),
            file_name=f"escala_hc15_{ANO}_{MES:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

aba_escala, aba_dashboard = st.tabs(["📋 Escala mensal", "📊 Dashboard de dimensionamento"])
with aba_escala:
    exibir_grade_mensal()
    _, mensagens, _ = auditar_escala(st.session_state.escala)
    if mensagens:
        with st.expander(f"⚠️ {len(mensagens)} alerta(s) de consistência e cobertura", expanded=True):
            for mensagem in mensagens[:20]:
                st.write(f"• {mensagem}")
            if len(mensagens) > 20:
                st.caption(f"Mostrando 20 de {len(mensagens)} alertas.")
    else:
        st.success("A escala atende às regras e à cobertura configuradas neste protótipo.")
with aba_dashboard:
    dashboard()

st.divider()
st.caption(
    "Protótipo operacional: antes de uso assistencial real, valide metas de carga horária, cobertura mínima, "
    "regras sindicais/legais e governança de acesso com RH, enfermagem e TI."
)

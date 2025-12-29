#!/usr/bin/env python3
"""
Aplicação Streamlit para análise individual de notas fiscais em PDFs.
Permite upload de um PDF e exibe os resultados da análise em tempo real.
"""

import streamlit as st
import os
import sys
import base64
import json
import time
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv
import requests
import PyPDF2
import pandas as pd
from datetime import datetime
from io import BytesIO
from streamlit_pdf_viewer import pdf_viewer

from config import (
    LIMITE_TAMANHO_PDF_MB,
    TIMEOUT_API_SEGUNDOS,
    TOLERANCIA_COMPARACAO_VALORES,
    TIPOS_DOCUMENTOS_VALIDOS,
    GEMINI_MODEL,
    GEMINI_TEMPERATURE,
    GEMINI_TOP_P,
    GEMINI_TOP_K,
    GEMINI_MAX_OUTPUT_TOKENS,
    BIGQUERY_ENABLED,
    BIGQUERY_PROJECT_ID,
    BIGQUERY_DATASET,
    BIGQUERY_TABLE
)

# Carrega variáveis de ambiente
load_dotenv()

# Configuração do Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Configuração do BigQuery - permite sobrescrita via .env
BIGQUERY_CREDENTIALS_PATH = os.getenv('BIGQUERY_CREDENTIALS_PATH')
# Sobrescreve com valores do .env se existirem
BIGQUERY_PROJECT_ID = os.getenv('BIGQUERY_PROJECT_ID', BIGQUERY_PROJECT_ID)
BIGQUERY_DATASET = os.getenv('BIGQUERY_DATASET', BIGQUERY_DATASET)
BIGQUERY_TABLE = os.getenv('BIGQUERY_TABLE', BIGQUERY_TABLE)

# Inicializa cliente BigQuery se habilitado
bigquery_client = None
bigquery_error_message = None

if BIGQUERY_ENABLED:
    if not BIGQUERY_CREDENTIALS_PATH:
        bigquery_error_message = "BIGQUERY_CREDENTIALS_PATH não está configurado no arquivo .env"
    else:
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account

            credentials_path = Path(BIGQUERY_CREDENTIALS_PATH)
            if not credentials_path.exists():
                bigquery_error_message = f"Arquivo de credenciais não encontrado: {BIGQUERY_CREDENTIALS_PATH}"
            else:
                credentials = service_account.Credentials.from_service_account_file(
                    str(credentials_path),
                    scopes=["https://www.googleapis.com/auth/bigquery"]
                )

                # Prioriza o BIGQUERY_PROJECT_ID do config.py/env em vez do arquivo de credenciais
                project_to_use = os.getenv('BIGQUERY_PROJECT_ID', BIGQUERY_PROJECT_ID)

                bigquery_client = bigquery.Client(
                    credentials=credentials,
                    project=project_to_use
                )

                # Atualiza as variáveis globais para refletir o projeto real sendo usado
                BIGQUERY_PROJECT_ID = project_to_use

                # Log de debug (será exibido no terminal do Streamlit)
                print(f"✓ BigQuery conectado: {BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}")
        except ImportError:
            bigquery_error_message = "Biblioteca google-cloud-bigquery não instalada. Execute: pip install google-cloud-bigquery"
        except Exception as e:
            bigquery_error_message = f"Erro ao conectar ao BigQuery: {str(e)}"


def contar_paginas_pdf(pdf_bytes: bytes) -> int:
    """Conta o número de páginas de um PDF."""
    try:
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
        return len(pdf_reader.pages)
    except Exception as e:
        st.error(f"Erro ao contar páginas: {e}")
        return 0


def pdf_para_base64(pdf_bytes: bytes) -> str:
    """Converte o PDF para base64."""
    try:
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        return pdf_base64
    except Exception as e:
        st.error(f"Erro ao converter PDF: {e}")
        return ""


def criar_prompt_extracao() -> str:
    """Cria o prompt para extração de informações."""
    return """Analise este documento PDF e extraia as informações de TODAS as notas fiscais encontradas.

Os seguintes documentos são considerados nota fiscal:
- Nota Fiscal (qualquer tipo)
- DANFE (Documento Auxiliar da Nota Fiscal Eletrônica)
- Faturas de telefonia (operadoras)
- Faturas de concessionárias (Light, CEG, Rioáguas, etc.)

Para CADA nota fiscal encontrada no documento, extraia as seguintes informações:

1. **numero_pagina**: número da página onde a nota fiscal se encontra
2. **cnpj_prestador**: CNPJ do prestador de serviço (somente números)
3. **tipo_documento**: tipo do documento (Nota Fiscal, DANFE, Fatura Telefonia, Fatura Concessionária, etc.)
4. **numero_nf**: número da nota fiscal
5. **valor_total**: valor total da nota fiscal (em formato numérico, ex: 1234.56)

IMPORTANTE:
- Se houver MÚLTIPLAS notas fiscais no mesmo PDF, retorne uma lista com todas elas
- Se NÃO encontrar nenhuma nota fiscal, retorne apenas: [{"erro": "nota fiscal não encontrada"}]

Retorne APENAS um array JSON válido no seguinte formato (sem markdown, sem explicações, apenas o JSON):

[
  {
    "numero_pagina": 1,
    "cnpj_prestador": "12345678000190",
    "tipo_documento": "DANFE",
    "numero_nf": "12345",
    "valor_total": 1500.00
  }
]"""


def processar_pdf_com_gemini(pdf_bytes: bytes, nome_arquivo: str) -> List[Dict[str, Any]]:
    """Processa um PDF usando o Gemini para extrair informações de notas fiscais."""
    try:
        # Verifica o tamanho do arquivo
        tamanho_mb = len(pdf_bytes) / (1024 * 1024)

        if tamanho_mb > LIMITE_TAMANHO_PDF_MB:
            return [{"erro": f"documento muito grande para análise ({tamanho_mb:.2f} MB - limite: {LIMITE_TAMANHO_PDF_MB} MB)"}]

        # Converte PDF para base64
        pdf_base64 = pdf_para_base64(pdf_bytes)

        if not pdf_base64:
            return [{"erro": "erro ao ler PDF"}]

        # Prepara o conteúdo para a API
        contents = [
            {"text": criar_prompt_extracao()},
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": pdf_base64
                }
            }
        ]

        # Prepara o payload para a API
        payload = {
            "contents": [{
                "parts": contents
            }],
            "generationConfig": {
                "temperature": GEMINI_TEMPERATURE,
                "topP": GEMINI_TOP_P,
                "topK": GEMINI_TOP_K,
                "maxOutputTokens": GEMINI_MAX_OUTPUT_TOKENS,
            }
        }

        # Faz a requisição à API do Gemini
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=TIMEOUT_API_SEGUNDOS
        )

        if response.status_code != 200:
            return [{"erro": f"erro na API: status {response.status_code}"}]

        # Parse da resposta
        resultado = response.json()

        if 'candidates' not in resultado or not resultado['candidates']:
            return [{"erro": "resposta da API inválida"}]

        resposta_texto = resultado['candidates'][0]['content']['parts'][0]['text'].strip()

        # Remove markdown se existir
        if resposta_texto.startswith('```json'):
            resposta_texto = resposta_texto.replace('```json', '').replace('```', '').strip()
        elif resposta_texto.startswith('```'):
            resposta_texto = resposta_texto.replace('```', '').strip()

        # Parse do JSON
        notas_fiscais = json.loads(resposta_texto)

        # Verifica se é uma lista
        if not isinstance(notas_fiscais, list):
            notas_fiscais = [notas_fiscais]

        return notas_fiscais

    except json.JSONDecodeError as e:
        return [{"erro": "erro ao processar JSON da resposta"}]
    except requests.exceptions.Timeout:
        return [{"erro": "timeout ao processar documento"}]
    except requests.exceptions.RequestException as e:
        return [{"erro": f"erro na requisição: {str(e)}"}]
    except Exception as e:
        erro_msg = str(e).lower()
        if any(palavra in erro_msg for palavra in ['size', 'large', 'too big', 'limit', 'quota', 'resource']):
            tamanho_mb = len(pdf_bytes) / (1024 * 1024)
            return [{"erro": f"documento muito grande para análise ({tamanho_mb:.2f} MB)"}]
        return [{"erro": f"erro ao processar: {str(e)}"}]


def consultar_bigquery_por_arquivo(nome_arquivo: str) -> List[Dict[str, Any]]:
    """Consulta o BigQuery para buscar TODOS os registros do arquivo processado."""
    global BIGQUERY_PROJECT_ID, BIGQUERY_DATASET, BIGQUERY_TABLE

    if not BIGQUERY_ENABLED or not bigquery_client:
        return []

    try:
        # Remove .pdf do nome se existir
        nome_sem_extensao = nome_arquivo.replace('.pdf', '').replace('.PDF', '')

        query = f"""
        SELECT
          descricao,
          num_documento,
          valor_documento,
          sum(valor_pago) as valor_pago_total
        FROM
          `{BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}`
        WHERE
          id_tipo_documento = "1"
          AND (descricao = '{nome_sem_extensao}'
               OR upper(descricao) = '{nome_sem_extensao.upper()}'
               OR descricao = '{nome_arquivo}'
               OR upper(descricao) = '{nome_arquivo.upper()}')
        GROUP BY 1, 2, 3
        """

        # Log de debug
        print(f"DEBUG - Consultando BigQuery:")
        print(f"  Projeto: {BIGQUERY_PROJECT_ID}")
        print(f"  Dataset: {BIGQUERY_DATASET}")
        print(f"  Tabela: {BIGQUERY_TABLE}")
        print(f"  Arquivo: {nome_arquivo}")

        # Executa a query
        query_job = bigquery_client.query(query)
        resultados_bq = list(query_job.result())

        # Retorna lista com todos os registros encontrados
        registros = []
        for row in resultados_bq:
            registros.append({
                'num_documento_bq': row.num_documento if row.num_documento else 'N/A',
                'valor_documento_bq': float(row.valor_documento) if row.valor_documento else 'N/A',
                'valor_pago_total_bq': float(row.valor_pago_total) if row.valor_pago_total else 'N/A'
            })

        return registros

    except Exception as e:
        st.warning(f"Erro ao consultar BigQuery: {e}")
        return []


def validar_nota_fiscal(nota: Dict[str, Any]) -> Dict[str, str]:
    """Valida uma nota fiscal com base nos dados do BigQuery."""

    # Verifica se há erro na nota fiscal
    if 'erro' in nota:
        return {
            'pdf_possui_nf_em_despesas': 'N/A',
            'valor_pago_menor_igual_declarado': 'N/A',
            'valor_nf_igual_declarado': 'N/A',
            'classificacao_final': 'Não foi possível analisar'
        }

    # Verifica se encontrou nota fiscal válida no PDF
    tipo_doc = str(nota.get('tipo_documento', '')).strip().lower()
    possui_documento_valido = any(tipo in tipo_doc for tipo in TIPOS_DOCUMENTOS_VALIDOS) and tipo_doc != ''

    if not possui_documento_valido:
        return {
            'pdf_possui_nf_em_despesas': 'N/A',
            'valor_pago_menor_igual_declarado': 'N/A',
            'valor_nf_igual_declarado': 'N/A',
            'classificacao_final': 'Não foi possível analisar'
        }

    # Validação 1: PDF possui NF declarada em Despesas
    num_documento_bq = nota.get('num_documento_bq', 'N/A')
    pdf_possui_nf = 'NÃO' if num_documento_bq == 'N/A' else 'SIM'

    # Se não tem no BigQuery, já é Suspeito
    if pdf_possui_nf == 'NÃO':
        return {
            'pdf_possui_nf_em_despesas': 'NÃO',
            'valor_pago_menor_igual_declarado': 'N/A',
            'valor_nf_igual_declarado': 'N/A',
            'classificacao_final': 'Suspeito'
        }

    # Validação 2: Valor Total Pago <= Valor Declarado em Despesas
    valor_pago_bq = nota.get('valor_pago_total_bq', 'N/A')
    valor_documento_bq = nota.get('valor_documento_bq', 'N/A')

    if valor_pago_bq == 'N/A' or valor_documento_bq == 'N/A':
        valor_pago_menor_igual = 'N/A'
    else:
        try:
            valor_pago_menor_igual = 'SIM' if float(valor_pago_bq) <= float(valor_documento_bq) else 'NÃO'
        except (ValueError, TypeError):
            valor_pago_menor_igual = 'N/A'

    # Validação 3: Valor total NF == Valor total declarado em Despesas
    valor_total_nf = nota.get('valor_total', 'N/A')

    if valor_total_nf == 'N/A' or valor_documento_bq == 'N/A':
        valor_nf_igual_declarado = 'N/A'
    else:
        try:
            diferenca = abs(float(valor_total_nf) - float(valor_documento_bq))
            valor_nf_igual_declarado = 'SIM' if diferenca < TOLERANCIA_COMPARACAO_VALORES else 'NÃO'
        except (ValueError, TypeError):
            valor_nf_igual_declarado = 'N/A'

    # Classificação Final
    respostas = [pdf_possui_nf, valor_pago_menor_igual, valor_nf_igual_declarado]

    if all(resp == 'SIM' for resp in respostas):
        classificacao = 'Descartado'
    elif 'NÃO' in respostas:
        classificacao = 'Suspeito'
    else:
        classificacao = 'Suspeito'

    return {
        'pdf_possui_nf_em_despesas': pdf_possui_nf,
        'valor_pago_menor_igual_declarado': valor_pago_menor_igual,
        'valor_nf_igual_declarado': valor_nf_igual_declarado,
        'classificacao_final': classificacao
    }


def formatar_valor_monetario(valor: Any) -> str:
    """Formata valor monetário com vírgula como separador decimal."""
    if valor == 'N/A' or valor == 'ERRO' or valor == '' or valor is None:
        return valor if isinstance(valor, str) else 'N/A'

    try:
        valor_float = float(valor)
        return f"R$ {valor_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except (ValueError, TypeError):
        return str(valor)


def main():
    """Função principal do Streamlit."""

    # Configuração da página
    st.set_page_config(
        page_title="OSINFO - Prestação de Contas",
        page_icon="",
        layout="wide"
    )

    # Logo
    st.logo("img/iplan_vertical_azul.png", size="large")

    # CSS customizado para botão primário azul
    st.markdown("""
        <style>
        /* Botão primário azul */
        .stButton > button[kind="primary"] {
            background-color: #1E40AF;
            color: white;
            border: none;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #1E3A8A;
            border: none;
        }
        .stButton > button[kind="primary"]:active {
            background-color: #1E3A8A;
            border: none;
        }
        </style>
    """, unsafe_allow_html=True)

    # Título e descrição
    st.title("📄 OSINFO - Prestação de Contas")

    # Verifica se a API key está configurada
    if not GEMINI_API_KEY:
        st.error("❌ GEMINI_API_KEY não encontrada. Configure o arquivo .env")
        st.stop()

    # Inicializa estados da sessão
    if 'analise_concluida' not in st.session_state:
        st.session_state.analise_concluida = False
    if 'resultados' not in st.session_state:
        st.session_state.resultados = None
    if 'pdf_bytes' not in st.session_state:
        st.session_state.pdf_bytes = None
    if 'nome_arquivo' not in st.session_state:
        st.session_state.nome_arquivo = None
    if 'num_paginas' not in st.session_state:
        st.session_state.num_paginas = 0

    # Botão Nova Análise (só aparece após análise concluída)
    if st.session_state.analise_concluida:
        if st.button("🔄 Nova Análise", type="secondary"):
            st.session_state.analise_concluida = False
            st.session_state.resultados = None
            st.session_state.pdf_bytes = None
            st.session_state.nome_arquivo = None
            st.session_state.num_paginas = 0
            st.rerun()

    # Se análise não foi concluída, mostra upload e botão de análise
    if not st.session_state.analise_concluida:
        st.markdown("### 📤 Validação de Documentos")

        st.info("""
**📌 Tipos de documentos aceitos para análise**

Neste momento, o sistema realiza a conferência automática dos seguintes documentos:
* **Nota Fiscal de Serviços / Produto**
* **DANFE**
* **Faturas de Concessionárias** (Light, CEG, Rio Águas)

*Qualquer outro tipo de documento será classificado como 'Não foi possível analisar'.*
        """)

        # Upload do arquivo
        uploaded_file = st.file_uploader(
            label="Envie o PDF da sua prestação de contas abaixo para iniciar a conferência automática das Notas Fiscais",
            type=['pdf'],
            help=f"Tamanho máximo: {LIMITE_TAMANHO_PDF_MB} MB"
        )

        if uploaded_file is not None:
            # Lê o PDF
            pdf_bytes = uploaded_file.read()
            tamanho_mb = len(pdf_bytes) / (1024 * 1024)
            num_paginas = contar_paginas_pdf(pdf_bytes)

            # Botão de processar
            processar = st.button("🚀 Analisar PDF", type="primary")

            if processar:
                # Cria barra de progresso e status
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Etapa 1: Processamento com Gemini (0% -> 40%)
                status_text.text("🔄 Convertendo PDF para análise...")
                progress_bar.progress(10)

                status_text.text("🤖 Analisando PDF com Gemini AI...")
                progress_bar.progress(20)

                # Processa com Gemini
                notas_fiscais = processar_pdf_com_gemini(pdf_bytes, uploaded_file.name)

                progress_bar.progress(40)

                if notas_fiscais and 'erro' in notas_fiscais[0]:
                    progress_bar.empty()
                    status_text.empty()
                    st.error(f"❌ Erro: {notas_fiscais[0]['erro']}")
                else:
                    status_text.text("✅ Análise do Gemini concluída!")
                    progress_bar.progress(50)

                    # Consulta BigQuery
                    registros_bigquery = []
                    if bigquery_client:
                        status_text.text("🗄️ Consultando OSINFO...")
                        progress_bar.progress(60)

                        registros_bigquery = consultar_bigquery_por_arquivo(uploaded_file.name)

                        status_text.text("✅ Consulta ao OSINFO concluída!")
                        progress_bar.progress(70)
                    else:
                        progress_bar.progress(70)

                    # Processa e valida cada nota fiscal
                    status_text.text("🔍 Validando notas fiscais...")
                    progress_bar.progress(80)

                    resultados = []
                    total_notas = len(notas_fiscais)

                    for idx, nota in enumerate(notas_fiscais, 1):
                        # Atualiza progresso durante validação
                        progresso_validacao = 80 + int((idx / total_notas) * 15)
                        status_text.text(f"🔍 Validando nota fiscal {idx}/{total_notas}...")
                        progress_bar.progress(progresso_validacao)

                        # Remove zeros à esquerda do número da NF extraído pelo Gemini
                        if 'numero_nf' in nota and nota['numero_nf']:
                            numero_nf_original = str(nota['numero_nf']).strip()
                            # Remove zeros à esquerda, mas mantém se for só "0"
                            nota['numero_nf'] = numero_nf_original.lstrip('0') or '0'

                        # Matching com BigQuery
                        if registros_bigquery and 'erro' not in nota:
                            numero_nf_gemini = str(nota.get('numero_nf', '')).strip()

                            registro_matching = None
                            for reg_bq in registros_bigquery:
                                num_doc_bq = str(reg_bq.get('num_documento_bq', '')).strip()
                                if num_doc_bq == numero_nf_gemini:
                                    registro_matching = reg_bq
                                    break

                            if registro_matching:
                                nota.update(registro_matching)
                            else:
                                # Não encontrou match - marca como N/A
                                nota['num_documento_bq'] = 'N/A'
                                nota['valor_documento_bq'] = 'N/A'
                                nota['valor_pago_total_bq'] = 'N/A'
                        else:
                            nota['num_documento_bq'] = 'N/A'
                            nota['valor_documento_bq'] = 'N/A'
                            nota['valor_pago_total_bq'] = 'N/A'

                        # Valida
                        validacoes = validar_nota_fiscal(nota)
                        nota.update(validacoes)
                        resultados.append(nota)

                    # Finaliza progresso
                    progress_bar.progress(100)
                    status_text.text("✅ Processamento concluído!")
                    time.sleep(0.5)
                    progress_bar.empty()
                    status_text.empty()

                    # Salva resultados no session_state
                    st.session_state.resultados = resultados
                    st.session_state.pdf_bytes = pdf_bytes
                    st.session_state.nome_arquivo = uploaded_file.name
                    st.session_state.num_paginas = num_paginas
                    st.session_state.registros_bigquery = registros_bigquery
                    st.session_state.analise_concluida = True

                    # Recarrega a página para exibir resultados
                    st.rerun()

    # Se análise foi concluída, exibe as duas colunas com PDF e resultados
    if st.session_state.analise_concluida and st.session_state.resultados:
        # Cria layout de duas colunas
        col_esquerda, col_direita = st.columns([1, 1])

        with col_esquerda:
            st.header(" Visualização")

            # Container com borda para o visualizador de PDF
            with st.container(border=True):
                # Visualiza o PDF usando streamlit-pdf-viewer (muito mais eficiente para PDFs grandes)
                pdf_viewer(st.session_state.pdf_bytes, height=800)

        with col_direita:
            st.header("🔍 Análise")

            # Exibe informações do arquivo
            tamanho_mb = len(st.session_state.pdf_bytes) / (1024 * 1024)
            st.markdown(f"""
                <table style="width:100%; border:none;">
                    <tr style="border:none">
                        <td style="padding: 4px; border:none;"><strong>Arquivo</strong></td>
                        <td style="padding: 4px; border:none;"><strong>Tamanho</strong></td>
                        <td style="padding: 4px; border:none;"><strong>Páginas</strong></td>
                    </tr>
                    <tr style="border:none">
                        <td style="padding: 4px; border:none;">{st.session_state.nome_arquivo}</td>
                        <td style="padding: 4px; border:none;">{tamanho_mb:.2f} MB</td>
                        <td style="padding: 4px; border:none;">{st.session_state.num_paginas}</td>
                    </tr>
                </table>
            """, unsafe_allow_html=True)
            for idx, resultado in enumerate(st.session_state.resultados, 1):
                # Prepara a badge de classificação
                classificacao = resultado.get('classificacao_final', 'N/A')
                if classificacao == 'Descartado':
                    badge_color = '#d4edda'
                    badge_text_color = '#155724'
                    icon = '✅'
                elif classificacao == 'Suspeito':
                    badge_color = '#fff3cd'
                    badge_text_color = '#856404'
                    icon = '⚠️'
                else:
                    badge_color = '#fff3cd'
                    badge_text_color = '#856404'
                    icon = '❓'

                # Card com tabela de informações
                tipo_doc = resultado.get('tipo_documento', 'N/A')
                numero_nf = resultado.get('numero_nf', 'N/A')
                cnpj = resultado.get('cnpj_prestador', 'N/A')
                valor_total = formatar_valor_monetario(resultado.get('valor_total', 'N/A'))
                pagina = resultado.get('numero_pagina', 'N/A')

                # Prepara análise detalhada
                pdf_possui_nf = resultado.get('pdf_possui_nf_em_despesas', 'N/A')
                valor_pago_menor_igual = resultado.get('valor_pago_menor_igual_declarado', 'N/A')
                valor_nf_igual = resultado.get('valor_nf_igual_declarado', 'N/A')

                # Define ícones e textos baseados nas validações
                if pdf_possui_nf == 'SIM':
                    icon_existe = '✅'
                    texto_existe = 'Sim, nota encontrada nas despesas declaradas.'
                elif pdf_possui_nf == 'NÃO':
                    icon_existe = '❌'
                    texto_existe = 'Não, nota não consta nas despesas declaradas.'
                else:
                    icon_existe = '❓'
                    texto_existe = 'Não foi possível verificar.'

                if valor_pago_menor_igual == 'SIM':
                    icon_valor_pago = '✅'
                    texto_valor_pago = 'Sim'
                elif valor_pago_menor_igual == 'NÃO':
                    icon_valor_pago = '❌'
                    texto_valor_pago = 'Não'
                else:
                    icon_valor_pago = '❌'
                    texto_valor_pago = 'Não é possível verificar (nota não encontrada).' if pdf_possui_nf == 'NÃO' else 'Não foi possível verificar.'

                if valor_nf_igual == 'SIM':
                    icon_valor_nf = '✅'
                    texto_valor_nf = 'Sim'
                elif valor_nf_igual == 'NÃO':
                    icon_valor_nf = '❌'
                    texto_valor_nf = 'Não'
                else:
                    icon_valor_nf = '❌'
                    texto_valor_nf = 'Não é possível verificar (nota não encontrada).' if pdf_possui_nf == 'NÃO' else 'Não foi possível verificar.'

                # Usa container com estilo de card
                with st.container(border=True):
                    # Aplica estilo de card ao container
                    st.markdown(f"""
                    <style>
                        div[data-testid="stVerticalBlock"] > div:has(> div.nota-fiscal-card-{idx}) {{
                            border: 1px solid #ddd;
                            border-radius: 8px;
                            padding: 16px;
                            margin-bottom: 16px;
                            background-color: #ffffff;
                        }}
                    </style>
                    <div class="nota-fiscal-card-{idx}">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                            <h5 style="margin: 0;">{tipo_doc} - {numero_nf}</h5>
                            <div style="background-color: {badge_color}; color: {badge_text_color}; padding: 6px 12px; border-radius: 6px; font-weight: bold;">
                                {icon} {classificacao}
                            </div>
                        </div>
                        <table style="width:100%; border-collapse: collapse; border:none; margin-bottom: 16px;">
                            <tr>
                                <td style="padding: 8px; font-weight: bold;">CNPJ Prestador:</td>
                                <td colspan="3" style="padding: 8px;">{cnpj}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px; font-weight: bold;">Valor Total:</td>
                                <td style="padding: 8px;">{valor_total}</td>
                                <td style="padding: 8px; font-weight: bold;">Página:</td>
                                <td style="padding: 8px;">{pagina}</td>
                            </tr>
                        </table>
                    </div>
                    """, unsafe_allow_html=True)

                    # Expander com análise final dentro do container
                    with st.expander("📊 Análise Detalhada"):
                        st.markdown(f"""
                        {icon_existe} **1. Existe no OSINFO?** {texto_existe}

                        {icon_valor_pago} **2. Valor Pago ≤ Declarado?** {texto_valor_pago}

                        {icon_valor_nf} **3. Valor da Nota Fiscal é igual ao Valor Declarado?** {texto_valor_nf}
                        """)

                        # Se encontrou a nota no BigQuery, exibe tabela com os dados
                        if pdf_possui_nf == 'SIM':
                            st.markdown("**Dados encontrados no OSINFO:**")

                            # Prepara dados para a tabela
                            dados_bq = {
                                'Campo': [
                                    'Número do Documento',
                                    'Valor Documento Declarado',
                                    'Valor Pago Total'
                                ],
                                'Valor': [
                                    resultado.get('num_documento_bq', 'N/A'),
                                    formatar_valor_monetario(resultado.get('valor_documento_bq', 'N/A')),
                                    formatar_valor_monetario(resultado.get('valor_pago_total_bq', 'N/A'))
                                ]
                            }

                            df_bq = pd.DataFrame(dados_bq)
                            st.table(df_bq)

            # Container separado para exibir outras despesas do BigQuery (quando houver registros mas sem match)
            if 'registros_bigquery' in st.session_state and st.session_state.registros_bigquery:
                # Coleta TODOS os números de notas fiscais extraídos do PDF (independente se deram match ou não)
                numeros_nf_no_pdf = set()
                for resultado in st.session_state.resultados:
                    if 'erro' not in resultado:
                        numero_nf = str(resultado.get('numero_nf', '')).strip()
                        if numero_nf and numero_nf != 'N/A' and numero_nf != '':
                            numeros_nf_no_pdf.add(numero_nf)

                # Filtra apenas os registros do BigQuery que NÃO correspondem a nenhuma nota fiscal do PDF
                dados_outras_despesas = []
                for reg in st.session_state.registros_bigquery:
                    num_doc_bq = str(reg.get('num_documento_bq', '')).strip()

                    # Inclui se:
                    # 1. O número do documento é NULL/vazio/N/A (não pode ter match)
                    # 2. OU se o número do documento NÃO está na lista de notas do PDF
                    if not num_doc_bq or num_doc_bq == 'N/A' or num_doc_bq not in numeros_nf_no_pdf:
                        dados_outras_despesas.append({
                            'Número Documento': reg.get('num_documento_bq', 'N/A') if reg.get('num_documento_bq') else 'N/A',
                            'Valor Documento': formatar_valor_monetario(reg.get('valor_documento_bq', 'N/A')),
                            'Valor Pago Total': formatar_valor_monetario(reg.get('valor_pago_total_bq', 'N/A'))
                        })

                # Só exibe o container se houver despesas não encontradas no PDF
                if dados_outras_despesas:
                    with st.container(border=True):
                        st.markdown("### 📋 Outras despesas encontradas no OSINFO")
                        st.markdown("As seguintes despesas foram encontradas para este arquivo, mas não deram match com as notas fiscais extraídas:")

                        df_outras_despesas = pd.DataFrame(dados_outras_despesas)
                        st.dataframe(df_outras_despesas, use_container_width=True, hide_index=True)

            # Exportar para Excel
            st.markdown("---")

            # Prepara dados para DataFrame
            dados_exportar = []
            for resultado in st.session_state.resultados:
                dados_exportar.append({
                    'Nome do Arquivo': st.session_state.nome_arquivo,
                    'Total de Páginas': st.session_state.num_paginas,
                    'Número da Página': resultado.get('numero_pagina', 'N/A'),
                    'CNPJ Prestador': resultado.get('cnpj_prestador', 'N/A'),
                    'Tipo de Documento': resultado.get('tipo_documento', 'N/A'),
                    'Número da NF': resultado.get('numero_nf', 'N/A'),
                    'Valor Total da NF': formatar_valor_monetario(resultado.get('valor_total', 'N/A')),
                    'Num Documento (BQ)': resultado.get('num_documento_bq', 'N/A'),
                    'Valor Documento (BQ)': formatar_valor_monetario(resultado.get('valor_documento_bq', 'N/A')),
                    'Valor Pago Total (BQ)': formatar_valor_monetario(resultado.get('valor_pago_total_bq', 'N/A')),
                    'PDF possui NF em Despesas?': resultado.get('pdf_possui_nf_em_despesas', 'N/A'),
                    'Valor Pago <= Valor Declarado?': resultado.get('valor_pago_menor_igual_declarado', 'N/A'),
                    'Valor NF == Valor Declarado?': resultado.get('valor_nf_igual_declarado', 'N/A'),
                    'Classificação Final': resultado.get('classificacao_final', 'N/A')
                })

            df = pd.DataFrame(dados_exportar)

            # Gera Excel em memória
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Análise')
            output.seek(0)

            # Botão de download
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arquivo_excel = f"analise_nf_{timestamp}.xlsx"

            st.download_button(
                label="📥 Download Excel",
                data=output,
                file_name=nome_arquivo_excel,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=False
            )


if __name__ == "__main__":
    main()

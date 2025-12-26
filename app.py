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
        page_icon="📄",
        layout="wide"
    )

    # Título e descrição
    st.title("📄 OSINFO - Prestação de Contas")

    # Verifica se a API key está configurada
    if not GEMINI_API_KEY:
        st.error("❌ GEMINI_API_KEY não encontrada. Configure o arquivo .env")
        st.stop()


    # Upload do arquivo
    uploaded_file = st.file_uploader(
        "📎 Faça upload de uma Prestação de Contas para validar as Notas Fiscais",
        type=['pdf'],
        help=f"Tamanho máximo: {LIMITE_TAMANHO_PDF_MB} MB"
    )

    if uploaded_file is not None:
        # Lê o PDF
        pdf_bytes = uploaded_file.read()
        tamanho_mb = len(pdf_bytes) / (1024 * 1024)
        num_paginas = contar_paginas_pdf(pdf_bytes)

        # Cria layout de duas colunas desde o início
        col_esquerda, col_direita = st.columns([1, 1])

        with col_esquerda:
            st.header("📄 Visualização")

            # Visualiza o PDF usando iframe
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{pdf_base64}" width="100%" height="800" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)

        with col_direita:
            st.header("🤖 Análise IA")

            # Informações do arquivo
            st.markdown(f"""
                <table style="width:100%; border-collapse: collapse; border:none; margin-top: 12px;">
                    <tr>
                        <td><strong>Nome do Arquivo</strong><br>{uploaded_file.name}</td>
                        <td><strong>Tamanho</strong><br>{tamanho_mb:.2f}</td>
                        <td><strong>Número de Páginas</strong><br>{num_paginas}</td>
                    </tr>
                </table>
            """, unsafe_allow_html=True)

            # Botão de processar na coluna direita
            processar = st.button("🚀 Analisar PDF", type="primary", use_container_width=False)

            if processar:
                # Cria barra de progresso e status
                with col_direita:
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    # Etapa 1: Processamento com Gemini (0% -> 40%)
                    status_text.text("🔄 Convertendo PDF para análise...")
                    progress_bar.progress(10)

                    status_text.text("🤖 Analisando PDF com Gemini AI...")
                    progress_bar.progress(20)

                # Processa com Gemini
                notas_fiscais = processar_pdf_com_gemini(pdf_bytes, uploaded_file.name)

                with col_direita:
                    progress_bar.progress(40)

                if notas_fiscais and 'erro' in notas_fiscais[0]:
                    with col_direita:
                        progress_bar.empty()
                        status_text.empty()
                        st.error(f"❌ Erro: {notas_fiscais[0]['erro']}")
                else:
                    with col_direita:
                        status_text.text("✅ Análise do Gemini concluída!")
                        progress_bar.progress(50)

                    # Consulta BigQuery
                    registros_bigquery = []
                    if bigquery_client:
                        with col_direita:
                            status_text.text("🗄️ Consultando BigQuery...")
                            progress_bar.progress(60)

                        registros_bigquery = consultar_bigquery_por_arquivo(uploaded_file.name)

                        with col_direita:
                            status_text.text("✅ Consulta ao BigQuery concluída!")
                            progress_bar.progress(70)
                    else:
                        with col_direita:
                            progress_bar.progress(70)

                    # Processa e valida cada nota fiscal
                    with col_direita:
                        status_text.text("🔍 Validando notas fiscais...")
                        progress_bar.progress(80)

                    resultados = []
                    total_notas = len(notas_fiscais)

                    for idx, nota in enumerate(notas_fiscais, 1):
                        # Atualiza progresso durante validação
                        progresso_validacao = 80 + int((idx / total_notas) * 15)
                        with col_direita:
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
                            elif registros_bigquery:
                                nota.update(registros_bigquery[0])
                        else:
                            nota['num_documento_bq'] = 'N/A'
                            nota['valor_documento_bq'] = 'N/A'
                            nota['valor_pago_total_bq'] = 'N/A'

                        # Valida
                        validacoes = validar_nota_fiscal(nota)
                        nota.update(validacoes)
                        resultados.append(nota)

                    # Finaliza progresso
                    with col_direita:
                        progress_bar.progress(100)
                        status_text.text("✅ Processamento concluído!")
                        time.sleep(0.5)
                        progress_bar.empty()
                        status_text.empty()

                    # Exibe resultados na coluna direita
                    with col_direita:
                        # Informações Analisadas (direto, sem seção de processamento)
                        st.subheader("📋 Informações Analisadas")

                        # Prepara dados para a tabela
                        dados_tabela = []
                        for resultado in resultados:
                            dados_tabela.append({
                                'Pág': resultado.get('numero_pagina', 'N/A'),
                                'Tipo': resultado.get('tipo_documento', 'N/A'),
                                'Nº NF': resultado.get('numero_nf', 'N/A'),
                                'CNPJ Prestador': resultado.get('cnpj_prestador', 'N/A'),
                                'Valor Total NF': formatar_valor_monetario(resultado.get('valor_total', 'N/A')),
                                'Classificação': resultado.get('classificacao_final', 'N/A')
                            })

                        # Cria DataFrame
                        df_resumo = pd.DataFrame(dados_tabela)

                        # Função para colorir a classificação
                        def colorir_classificacao(val):
                            if val == 'Descartado':
                                return 'background-color: #d4edda; color: #155724; font-weight: bold'
                            elif val == 'Suspeito':
                                return 'background-color: #f8d7da; color: #721c24; font-weight: bold'
                            else:
                                return 'background-color: #fff3cd; color: #856404; font-weight: bold'

                        # Aplica estilo
                        df_estilizado = df_resumo.style.applymap(
                            colorir_classificacao,
                            subset=['Classificação']
                        ).set_properties(**{
                            'text-align': 'left',
                            'font-size': '14px',
                            'border': '1px solid #ddd'
                        }).set_table_styles([
                            {'selector': 'th',
                             'props': [('background-color', '#1f77b4'),
                                      ('color', 'white'),
                                      ('font-weight', 'bold'),
                                      ('text-align', 'left'),
                                      ('padding', '12px 8px'),
                                      ('border', '1px solid #ddd')]},
                            {'selector': 'td',
                             'props': [('padding', '12px 8px'),
                                      ('border', '1px solid #ddd')]},
                            {'selector': 'tr:nth-of-type(even)',
                             'props': [('background-color', '#f3f3f3')]},
                            {'selector': 'tr:hover',
                             'props': [('background-color', '#e8f4f8')]}
                        ])

                        # Exibe a tabela estilizada
                        st.dataframe(df_estilizado, use_container_width=True, hide_index=True)

                        # Dropdowns com detalhes de cada nota
                        st.markdown("---")
                        st.markdown("### 🔍 Detalhes das Notas Fiscais")

                        for idx, resultado in enumerate(resultados, 1):
                            with st.expander(f"📋 Detalhes - Nota Fiscal #{idx} (Pág {resultado.get('numero_pagina', 'N/A')})", expanded=False):

                                # Classificação
                                classificacao = resultado.get('classificacao_final', 'N/A')
                                if classificacao == 'Descartado':
                                    st.success(f"✅ **Classificação:** {classificacao}")
                                elif classificacao == 'Suspeito':
                                    st.error(f"⚠️ **Classificação:** {classificacao}")
                                else:
                                    st.warning(f"❓ **Classificação:** {classificacao}")

                                st.divider()

                                # Informações extraídas do PDF
                                st.markdown("**📄 Dados Extraídos (Gemini)**")
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Página:** {resultado.get('numero_pagina', 'N/A')}")
                                    st.write(f"**Tipo de Documento:** {resultado.get('tipo_documento', 'N/A')}")
                                    st.write(f"**CNPJ Prestador:** {resultado.get('cnpj_prestador', 'N/A')}")
                                with col2:
                                    st.write(f"**Número da NF:** {resultado.get('numero_nf', 'N/A')}")
                                    st.write(f"**Valor Total:** {formatar_valor_monetario(resultado.get('valor_total', 'N/A'))}")

                                st.divider()

                                # Dados do BigQuery
                                if bigquery_client:
                                    st.markdown("**🗄️ Dados do BigQuery**")

                                    # Indica se houve matching
                                    num_nf_gemini = str(resultado.get('numero_nf', '')).strip()
                                    num_doc_bq = str(resultado.get('num_documento_bq', '')).strip()

                                    if num_doc_bq != 'N/A':
                                        if num_nf_gemini == num_doc_bq:
                                            st.info("🎯 Matching encontrado")
                                        else:
                                            st.warning("⚠️ Sem matching exato")

                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.write(f"**Num Documento:** {resultado.get('num_documento_bq', 'N/A')}")
                                        st.write(f"**Valor Documento:** {formatar_valor_monetario(resultado.get('valor_documento_bq', 'N/A'))}")
                                    with col2:
                                        st.write(f"**Valor Pago Total:** {formatar_valor_monetario(resultado.get('valor_pago_total_bq', 'N/A'))}")

                                    st.divider()

                                    # Validações
                                    st.markdown("**✅ Validações**")

                                    validacao1 = resultado.get('pdf_possui_nf_em_despesas', 'N/A')
                                    icon1 = "✅" if validacao1 == "SIM" else "❌" if validacao1 == "NÃO" else "❓"
                                    st.write(f"{icon1} **NF em Despesas:** {validacao1}")

                                    validacao2 = resultado.get('valor_pago_menor_igual_declarado', 'N/A')
                                    icon2 = "✅" if validacao2 == "SIM" else "❌" if validacao2 == "NÃO" else "❓"
                                    st.write(f"{icon2} **Valor Pago ≤ Declarado:** {validacao2}")

                                    validacao3 = resultado.get('valor_nf_igual_declarado', 'N/A')
                                    icon3 = "✅" if validacao3 == "SIM" else "❌" if validacao3 == "NÃO" else "❓"
                                    st.write(f"{icon3} **Valor NF = Declarado:** {validacao3}")

                        # Exportar para Excel
                        st.divider()
                        st.subheader("📥 Exportar Resultados")

                        # Prepara dados para DataFrame
                        dados_exportar = []
                        for resultado in resultados:
                            dados_exportar.append({
                                'Nome do Arquivo': uploaded_file.name,
                                'Total de Páginas': num_paginas,
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
                            use_container_width=True
                        )


if __name__ == "__main__":
    main()

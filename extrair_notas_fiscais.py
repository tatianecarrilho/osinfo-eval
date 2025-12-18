#!/usr/bin/env python3
"""
Script para extrair informações de notas fiscais de PDFs usando Google Gemini.
Versão compatível com Python 3.8+
"""

import os
import sys
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from dotenv import load_dotenv
import requests
import PyPDF2
import pandas as pd
from datetime import datetime

# Carrega variáveis de ambiente
load_dotenv()

# Configuração do Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
GEMINI_TEMPERATURE = float(os.getenv('GEMINI_TEMPERATURE', '0.1'))

if not GEMINI_API_KEY:
    print("ERRO: GEMINI_API_KEY não encontrada no arquivo .env")
    sys.exit(1)

# Configuração do BigQuery (opcional)
BIGQUERY_ENABLED = os.getenv('BIGQUERY_ENABLED', 'false').lower() == 'true'
BIGQUERY_PROJECT_ID = os.getenv('BIGQUERY_PROJECT_ID', 'rj-cvl')  # Valor padrão
BIGQUERY_DATASET = os.getenv('BIGQUERY_DATASET', 'adm_contrato_gestao')  # Valor padrão
BIGQUERY_TABLE = os.getenv('BIGQUERY_TABLE', 'despesas')  # Valor padrão
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', '')

# URL da API do Gemini
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Inicializa cliente BigQuery se habilitado
bigquery_client = None
if BIGQUERY_ENABLED:
    try:
        from google.cloud import bigquery

        # Configura credenciais se fornecidas
        if GOOGLE_APPLICATION_CREDENTIALS:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_APPLICATION_CREDENTIALS
            bigquery_client = bigquery.Client(project=BIGQUERY_PROJECT_ID)
        else:
            # Tenta usar credenciais do ambiente (gcloud CLI ou Application Default Credentials)
            bigquery_client = bigquery.Client(project=BIGQUERY_PROJECT_ID)

        print(f"✓ BigQuery habilitado: {BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}")
    except ImportError:
        print("⚠️  AVISO: google-cloud-bigquery não instalado. Execute: pip install google-cloud-bigquery")
        BIGQUERY_ENABLED = False
    except Exception as e:
        print(f"⚠️  AVISO: Erro ao conectar com BigQuery: {e}")
        print("         Verifique se você está autenticado com 'gcloud auth application-default login'")
        BIGQUERY_ENABLED = False


def contar_paginas_pdf(caminho_pdf: str) -> int:
    """Conta o número de páginas de um PDF."""
    try:
        with open(caminho_pdf, 'rb') as arquivo:
            leitor = PyPDF2.PdfReader(arquivo)
            return len(leitor.pages)
    except Exception as e:
        print(f"Erro ao contar páginas de {caminho_pdf}: {e}")
        return 0


def pdf_para_base64(caminho_pdf: str) -> str:
    """Converte o PDF para base64."""
    try:
        with open(caminho_pdf, 'rb') as arquivo:
            pdf_bytes = arquivo.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
            return pdf_base64
    except Exception as e:
        print(f"  ERRO ao ler PDF: {e}")
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
  },
  {
    "numero_pagina": 3,
    "cnpj_prestador": "98765432000111",
    "tipo_documento": "Nota Fiscal",
    "numero_nf": "67890",
    "valor_total": 2300.50
  }
]"""


def processar_pdf_com_gemini(caminho_pdf: str) -> List[Dict[str, Any]]:
    """Processa um PDF usando o Gemini para extrair informações de notas fiscais."""
    try:
        print(f"  Processando com Gemini: {os.path.basename(caminho_pdf)}")

        # Verifica o tamanho do arquivo
        tamanho_mb = os.path.getsize(caminho_pdf) / (1024 * 1024)
        print(f"  Tamanho do arquivo: {tamanho_mb:.2f} MB")

        # Limite de tamanho (ajuste conforme necessário)
        limite_tamanho_mb = 100

        if tamanho_mb > limite_tamanho_mb:
            print(f"  ⚠️  AVISO: Arquivo muito grande ({tamanho_mb:.2f} MB)")
            return [{"erro": f"documento muito grande para análise ({tamanho_mb:.2f} MB - limite: {limite_tamanho_mb} MB)"}]

        # Converte PDF para base64
        print(f"  Preparando PDF para envio...")
        pdf_base64 = pdf_para_base64(caminho_pdf)

        if not pdf_base64:
            return [{"erro": "erro ao ler PDF"}]

        print(f"  Enviando PDF para análise do Gemini...")

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
                "topP": 0.95,
                "topK": 64,
                "maxOutputTokens": 8192,
            }
        }

        # Faz a requisição à API do Gemini
        print(f"  Enviando para API do Gemini...")
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=120
        )

        if response.status_code != 200:
            print(f"  ERRO: API retornou status {response.status_code}")
            print(f"  Resposta: {response.text[:500]}")
            return [{"erro": f"erro na API: status {response.status_code}"}]

        # Parse da resposta
        resultado = response.json()

        if 'candidates' not in resultado or not resultado['candidates']:
            print(f"  ERRO: Resposta da API sem candidatos")
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
        print(f"  ERRO: Resposta não é um JSON válido: {e}")
        print(f"  Resposta recebida: {resposta_texto[:200]}...")
        return [{"erro": "erro ao processar JSON da resposta"}]
    except requests.exceptions.Timeout:
        print(f"  ERRO: Timeout ao processar o documento")
        return [{"erro": "timeout ao processar documento"}]
    except requests.exceptions.RequestException as e:
        print(f"  ERRO: Erro na requisição à API: {e}")
        return [{"erro": f"erro na requisição: {str(e)}"}]
    except Exception as e:
        erro_msg = str(e).lower()

        # Verifica se o erro está relacionado ao tamanho do arquivo
        if any(palavra in erro_msg for palavra in ['size', 'large', 'too big', 'limit', 'quota', 'resource']):
            print(f"  ERRO: Documento muito grande para análise")
            tamanho_mb = os.path.getsize(caminho_pdf) / (1024 * 1024)
            return [{"erro": f"documento muito grande para análise ({tamanho_mb:.2f} MB)"}]

        print(f"  ERRO ao processar PDF: {e}")
        return [{"erro": f"erro ao processar: {str(e)}"}]


def processar_todos_pdfs(pasta_pdfs: str) -> List[Dict[str, Any]]:
    """Processa todos os PDFs na pasta especificada."""
    pasta = Path(pasta_pdfs)

    if not pasta.exists():
        print(f"ERRO: Pasta {pasta_pdfs} não encontrada")
        sys.exit(1)

    # Lista todos os PDFs
    arquivos_pdf = sorted(pasta.glob('*.pdf'))

    if not arquivos_pdf:
        print(f"ERRO: Nenhum arquivo PDF encontrado em {pasta_pdfs}")
        sys.exit(1)

    print(f"\nEncontrados {len(arquivos_pdf)} arquivos PDF para processar\n")

    resultados = []

    for idx, caminho_pdf in enumerate(arquivos_pdf, 1):
        print(f"[{idx}/{len(arquivos_pdf)}] Processando: {caminho_pdf.name}")

        # Conta páginas do PDF
        num_paginas = contar_paginas_pdf(str(caminho_pdf))
        print(f"  Páginas: {num_paginas}")

        # Processa com Gemini
        notas_fiscais = processar_pdf_com_gemini(str(caminho_pdf))

        # Consulta BigQuery se habilitado
        registros_bigquery = []
        if BIGQUERY_ENABLED:
            print(f"  Consultando BigQuery...")
            registros_bigquery = consultar_bigquery_por_arquivo(caminho_pdf.name)
            if registros_bigquery:
                print(f"  ✓ Encontrado {len(registros_bigquery)} registro(s) no BigQuery")
            else:
                print(f"  ⚠️  Não encontrado no BigQuery")

        # Processa cada nota fiscal encontrada pelo Gemini
        for nota in notas_fiscais:
            nota['nome_arquivo'] = caminho_pdf.name
            nota['total_paginas_pdf'] = num_paginas

            # Se tem dados do BigQuery, processa a lógica de matching
            if registros_bigquery and 'erro' not in nota:
                numero_nf_gemini = str(nota.get('numero_nf', '')).strip()

                # Separa registros que batem e que não batem com o número da NF
                registro_matching = None
                registros_nao_matching = []

                for reg_bq in registros_bigquery:
                    num_doc_bq = str(reg_bq.get('num_documento_bq', '')).strip()
                    if num_doc_bq == numero_nf_gemini:
                        registro_matching = reg_bq
                    else:
                        registros_nao_matching.append(reg_bq)

                # Adiciona registro que bate na mesma linha
                if registro_matching:
                    nota.update(registro_matching)
                else:
                    # Se não achou matching, usa o primeiro registro do BQ na linha do Gemini
                    if registros_nao_matching:
                        nota.update(registros_nao_matching[0])
                        registros_nao_matching = registros_nao_matching[1:]

                # Adiciona a primeira linha (com dados do Gemini)
                resultados.append(nota)

                # Adiciona linhas extras para registros do BQ que não batem
                for reg_extra in registros_nao_matching:
                    linha_extra = {
                        'nome_arquivo': caminho_pdf.name,
                        'total_paginas_pdf': num_paginas,
                        'numero_pagina': '',
                        'cnpj_prestador': '',
                        'tipo_documento': '',
                        'numero_nf': '',
                        'valor_total': '',
                    }
                    linha_extra.update(reg_extra)
                    resultados.append(linha_extra)
            else:
                # Sem BigQuery ou com erro, adiciona normalmente
                if not registros_bigquery:
                    nota['num_documento_bq'] = 'N/A'
                    nota['valor_documento_bq'] = 'N/A'
                    nota['valor_pago_total_bq'] = 'N/A'
                resultados.append(nota)

        print(f"  ✓ Encontradas {len(notas_fiscais)} nota(s) fiscal(is)\n")

    return resultados


def consultar_bigquery_por_arquivo(nome_arquivo: str) -> List[Dict[str, Any]]:
    """Consulta o BigQuery para buscar TODOS os registros do arquivo processado."""
    if not BIGQUERY_ENABLED or not bigquery_client:
        return []

    try:
        # Remove .pdf do nome se existir para buscar com e sem extensão
        nome_sem_extensao = nome_arquivo.replace('.pdf', '').replace('.PDF', '')

        query = f"""
        SELECT
          descricao,
          num_documento,
          valor_documento,
          sum(valor_pago) as valor_pago_total
        FROM
          `{BIGQUERY_PROJECT_ID}.{BIGQUERY_DATASET}.despesas`
        WHERE
          id_tipo_documento = "1"
          AND (descricao = '{nome_sem_extensao}'
               OR upper(descricao) = '{nome_sem_extensao.upper()}'
               OR descricao = '{nome_arquivo}'
               OR upper(descricao) = '{nome_arquivo.upper()}')
        GROUP BY 1, 2, 3
        """

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
        print(f"  ⚠️  Erro ao consultar BigQuery para {nome_arquivo}: {e}")
        return []


def formatar_valor_monetario(valor: Any) -> str:
    """Formata valor monetário com vírgula como separador decimal (padrão brasileiro)."""
    if valor == 'N/A' or valor == 'ERRO' or valor == '' or valor is None:
        return valor if isinstance(valor, str) else 'N/A'

    try:
        # Converte para float se necessário
        valor_float = float(valor)
        # Formata com 2 casas decimais e vírgula
        return f"{valor_float:.2f}".replace('.', ',')
    except (ValueError, TypeError):
        return str(valor)


def gerar_planilha_excel(resultados: List[Dict[str, Any]], arquivo_saida: str):
    """Gera uma planilha Excel com os resultados."""

    # Prepara os dados para o DataFrame
    dados_formatados = []

    for resultado in resultados:
        if 'erro' in resultado:
            # Linha de erro
            dados_formatados.append({
                'Nome do Arquivo': resultado.get('nome_arquivo', 'N/A'),
                'Total de Páginas do PDF': resultado.get('total_paginas_pdf', 0),
                'Número da Página da NF': 'N/A',
                'CNPJ Prestador': 'N/A',
                'Tipo de Documento': 'N/A',
                'Número da NF': 'N/A',
                'Valor Total da NF': 'N/A',
                'Num Documento (BQ)': resultado.get('num_documento_bq', 'N/A'),
                'Valor Documento (BQ)': formatar_valor_monetario(resultado.get('valor_documento_bq', 'N/A')),
                'Valor Pago Total (BQ)': formatar_valor_monetario(resultado.get('valor_pago_total_bq', 'N/A')),
                'Observação': resultado['erro']
            })
        else:
            # Linha normal
            dados_formatados.append({
                'Nome do Arquivo': resultado.get('nome_arquivo', 'N/A'),
                'Total de Páginas do PDF': resultado.get('total_paginas_pdf', 0),
                'Número da Página da NF': resultado.get('numero_pagina', 'N/A'),
                'CNPJ Prestador': resultado.get('cnpj_prestador', 'N/A'),
                'Tipo de Documento': resultado.get('tipo_documento', 'N/A'),
                'Número da NF': resultado.get('numero_nf', 'N/A'),
                'Valor Total da NF': formatar_valor_monetario(resultado.get('valor_total', 'N/A')),
                'Num Documento (BQ)': resultado.get('num_documento_bq', 'N/A'),
                'Valor Documento (BQ)': formatar_valor_monetario(resultado.get('valor_documento_bq', 'N/A')),
                'Valor Pago Total (BQ)': formatar_valor_monetario(resultado.get('valor_pago_total_bq', 'N/A')),
                'Observação': ''
            })

    # Cria DataFrame
    df = pd.DataFrame(dados_formatados)

    # Salva em Excel
    df.to_excel(arquivo_saida, index=False, engine='openpyxl')
    print(f"\n✓ Planilha Excel gerada: {arquivo_saida}")


def main():
    """Função principal."""
    print("=" * 80)
    print("EXTRAÇÃO DE INFORMAÇÕES DE NOTAS FISCAIS - GOOGLE GEMINI")
    print("=" * 80)

    # Define pasta de PDFs
    pasta_pdfs = "files_100"

    # Processa todos os PDFs
    resultados = processar_todos_pdfs(pasta_pdfs)

    # Gera nome do arquivo de saída com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_saida = f"resultado_notas_fiscais_{timestamp}.xlsx"

    # Gera planilha Excel
    gerar_planilha_excel(resultados, arquivo_saida)

    print("\n" + "=" * 80)
    print(f"PROCESSAMENTO CONCLUÍDO!")
    print(f"Total de registros: {len(resultados)}")
    print("=" * 80)


if __name__ == "__main__":
    main()

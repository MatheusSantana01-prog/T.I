"""Regras de negócio do estoque (sem nada de Streamlit aqui).

Cada operação devolve (ok, mensagem) e só altera os dados quando está tudo válido.
"""
import copy
import io
import re
import secrets
import unicodedata
from datetime import datetime

import pandas as pd

from . import config
from .modelos import ItemTI

COLUNAS_HISTORICO = [
    "Data/Hora",
    "Equipamento",
    "Operação",
    "Quantidade",
    "Estoque Anterior",
    "Estoque Final",
    "Destino/Origem",
    "Detalhes",
    "Usuário",
]
MODO_SOMAR = "somar"
MODO_SUBSTITUIR = "substituir"
MODO_PULAR = "pular"


def agora_str():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def registrar(historico, equipamento, operacao, usuario, quantidade=None, anterior=None,
              final=None, destino="", detalhe="", data_hora=None):
    historico.append(
        {
            "Data/Hora": data_hora or agora_str(),
            "Equipamento": equipamento,
            "Operação": operacao,
            "Quantidade": quantidade,
            "Estoque Anterior": anterior,
            "Estoque Final": final,
            "Destino/Origem": destino,
            "Detalhes": detalhe,
            "Usuário": usuario,
        }
    )


def normalizar_series(entrada):
    """Aceita texto (uma série por linha, ou separadas por vírgula/;) ou lista."""
    if entrada is None:
        return []
    partes = re.split(r"[\n,;]+", entrada) if isinstance(entrada, str) else list(entrada)
    vistos, saida = set(), []
    for p in partes:
        s = str(p).strip().upper()
        if s and s not in vistos:
            vistos.add(s)
            saida.append(s)
    return saida


# ============================================================ movimentação
def movimentar(dados, nome, tipo, quantidade, usuario, destino="", series=None):
    """tipo: 'entrada', 'saida' ou 'ajuste'. 'destino' = setor/pessoa (saída) ou origem (entrada)."""
    item = dados["produtos"].get(nome)
    if item is None:
        return False, "Produto não encontrado."
    destino = (destino or "").strip()
    if tipo == "saida" and not destino:
        return False, "Informe o destino da saída (setor ou pessoa que recebeu)."
    if item.controla_serie:
        return _movimentar_serie(dados, item, tipo, usuario, destino, series)

    antes = item.estoque_atual
    quantidade = int(quantidade)
    if tipo == "entrada":
        if quantidade < 1:
            return False, "A quantidade precisa ser pelo menos 1."
        novo, operacao = antes + quantidade, "📥 Entrada"
    elif tipo == "saida":
        if quantidade < 1:
            return False, "A quantidade precisa ser pelo menos 1."
        if quantidade > antes:
            return False, f"Estoque insuficiente! O item possui apenas {antes} un."
        novo, operacao = antes - quantidade, "📤 Saída"
    elif tipo == "ajuste":
        if quantidade < 0:
            return False, "O estoque não pode ser negativo."
        novo, operacao = quantidade, "✏️ Ajuste Direto"
    else:
        return False, "Operação inválida."

    item.estoque_atual = novo
    registrar(dados["historico"], nome, operacao, usuario, quantidade, antes, novo, destino)
    return True, f"Estoque de '{nome}' atualizado: {antes} → {novo} un."


def _movimentar_serie(dados, item, tipo, usuario, destino, series):
    if tipo == "ajuste":
        return False, "Itens com número de série não aceitam ajuste direto. Registre entradas e saídas."
    series = normalizar_series(series)
    if not series:
        return False, "Informe pelo menos um número de série."
    antes = item.estoque_atual
    agora = agora_str()
    if tipo == "entrada":
        repetidas = [s for s in series if item.unidades.get(s, {}).get("situacao") == config.EM_ESTOQUE]
        if repetidas:
            return False, "Já estão em estoque: " + ", ".join(repetidas)
        for s in series:
            item.unidades[s] = {"situacao": config.EM_ESTOQUE, "destino": "", "data": agora}
        operacao = "📥 Entrada"
    elif tipo == "saida":
        fora = [s for s in series if item.unidades.get(s, {}).get("situacao") != config.EM_ESTOQUE]
        if fora:
            return False, "Não estão em estoque: " + ", ".join(fora)
        for s in series:
            item.unidades[s] = {"situacao": config.SAIU, "destino": destino, "data": agora}
        operacao = "📤 Saída"
    else:
        return False, "Operação inválida."
    item.sincronizar_estoque()
    registrar(dados["historico"], item.nome, operacao, usuario, len(series), antes,
              item.estoque_atual, destino, "Séries: " + ", ".join(series))
    return True, f"Estoque de '{item.nome}' atualizado: {antes} → {item.estoque_atual} un."


# ============================================================ transferência
def gerar_protocolo(agora=None):
    agora = agora or datetime.now()
    return f"TR-{agora:%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def transferir(filiais, origem, destino_filial, nome, quantidade, usuario, series=None,
               protocolo="", data_hora=None, recebedor=""):
    if origem == destino_filial:
        return False, "Escolha uma filial de destino diferente da origem."
    if origem not in filiais or destino_filial not in filiais:
        return False, "Filial não encontrada."
    f_o, f_d = filiais[origem], filiais[destino_filial]
    item_o = f_o["produtos"].get(nome)
    if item_o is None:
        return False, "Produto não encontrado na filial de origem."
    item_d = f_d["produtos"].get(nome)
    if item_d is not None and item_d.controla_serie != item_o.controla_serie:
        return False, "Na filial de destino esse produto é controlado de outra forma (com/sem número de série)."

    # ---- validação (nada é alterado antes de tudo estar certo)
    if item_o.controla_serie:
        series = normalizar_series(series)
        if not series:
            return False, "Escolha pelo menos um número de série."
        fora = [s for s in series if item_o.unidades.get(s, {}).get("situacao") != config.EM_ESTOQUE]
        if fora:
            return False, "Não estão em estoque na origem: " + ", ".join(fora)
        if item_d is not None:
            repetidas = [s for s in series if item_d.unidades.get(s, {}).get("situacao") == config.EM_ESTOQUE]
            if repetidas:
                return False, "Já constam em estoque no destino: " + ", ".join(repetidas)
        qtd = len(series)
    else:
        qtd = int(quantidade)
        if qtd < 1:
            return False, "A quantidade precisa ser pelo menos 1."
        if qtd > item_o.estoque_atual:
            return False, f"Estoque insuficiente na origem! Há apenas {item_o.estoque_atual} un."

    # ---- aplicação
    if item_d is None:
        item_d = ItemTI(nome, item_o.categoria, 0, item_o.estoque_minimo, item_o.controla_serie)
        f_d["produtos"][nome] = item_d
    antes_o, antes_d = item_o.estoque_atual, item_d.estoque_atual
    agora = data_hora or agora_str()
    partes = [f"Protocolo {protocolo}"] if protocolo else []
    if recebedor:
        partes.append(f"Recebedor: {recebedor}")
    if item_o.controla_serie:
        for s in series:
            item_o.unidades[s] = {"situacao": config.SAIU, "destino": f"Transferido para {destino_filial}", "data": agora}
            item_d.unidades[s] = {"situacao": config.EM_ESTOQUE, "destino": "", "data": agora}
        item_o.sincronizar_estoque()
        item_d.sincronizar_estoque()
        partes.append("Séries: " + ", ".join(series))
    else:
        item_o.estoque_atual -= qtd
        item_d.estoque_atual += qtd
    detalhe = "; ".join(partes)
    registrar(f_o["historico"], nome, "🔀 Transferência (saída)", usuario, qtd, antes_o,
              item_o.estoque_atual, destino_filial, detalhe, agora)
    registrar(f_d["historico"], nome, "🔀 Transferência (entrada)", usuario, qtd, antes_d,
              item_d.estoque_atual, origem, detalhe, agora)
    return True, f"{qtd} un. de '{nome}' transferida(s) de {origem} para {destino_filial}."


def transferir_lote(filiais, origem, destino_filial, itens, usuario, nome_usuario="",
                    recebedor_login="", recebedor_nome=""):
    """Transfere vários produtos de uma vez (tudo ou nada), com um protocolo único.

    itens: lista de {"equipamento", "quantidade", "series"}.
    Devolve (ok, mensagem, comprovante); o comprovante é None quando algo deu errado.
    """
    if not itens:
        return False, "A lista de transferência está vazia.", None
    if origem == destino_filial:
        return False, "Escolha uma filial de destino diferente da origem.", None
    if origem not in filiais or destino_filial not in filiais:
        return False, "Filial não encontrada.", None

    # ensaio numa cópia: se qualquer item falhar, nada é alterado de verdade
    teste = {n: copy.deepcopy(filiais[n]) for n in (origem, destino_filial)}
    for it in itens:
        ok, msg = transferir(teste, origem, destino_filial, it["equipamento"],
                             it.get("quantidade", 0), usuario, it.get("series"))
        if not ok:
            return False, f"{it['equipamento']}: {msg}", None

    agora = datetime.now()
    data_hora = agora.strftime("%d/%m/%Y %H:%M:%S")
    protocolo = gerar_protocolo(agora)
    recebedor_nome = (recebedor_nome or "").strip()
    recebedor = f"{recebedor_nome} ({recebedor_login})" if recebedor_login else recebedor_nome
    linhas = []
    for it in itens:
        item_o = filiais[origem]["produtos"][it["equipamento"]]
        series = normalizar_series(it.get("series")) if item_o.controla_serie else []
        qtd = len(series) if item_o.controla_serie else int(it["quantidade"])
        transferir(filiais, origem, destino_filial, it["equipamento"], qtd, usuario,
                   series or None, protocolo=protocolo, data_hora=data_hora, recebedor=recebedor)
        linhas.append({"equipamento": item_o.nome, "categoria": item_o.categoria,
                       "quantidade": qtd, "series": series})
    comprovante = {
        "protocolo": protocolo,
        "data_hora": data_hora,
        "origem": origem,
        "destino": destino_filial,
        "usuario": usuario,
        "usuario_nome": nome_usuario or usuario,
        "recebedor_login": recebedor_login,
        "recebedor_nome": recebedor_nome,
        "recebedor": recebedor,
        "itens": linhas,
    }
    return True, f"Transferência {protocolo} concluída: {len(linhas)} produto(s) de {origem} para {destino_filial}.", comprovante


_RE_PROTOCOLO = re.compile(r"Protocolo (TR-[\w-]+)")
_RE_SERIES = re.compile(r"Séries: (.*)$")
_RE_RECEBEDOR = re.compile(r"Recebedor: ([^;]*)")
COLUNAS_TRANSFERENCIAS = ["Protocolo", "Data", "Hora", "Origem", "Destino", "Equipamento",
                          "Quantidade", "Nº de série", "Enviado por", "Recebido por"]


def df_transferencias(filiais, nomes, nomes_usuarios=None):
    """Todas as transferências que envolvem as filiais de 'nomes' (mais recentes primeiro)."""
    nomes_usuarios = nomes_usuarios or {}
    vistos, linhas = set(), []
    for f in nomes:
        for h in filiais[f]["historico"]:
            op = h.get("Operação", "")
            if op == "🔀 Transferência (saída)":
                origem, destino = f, h.get("Destino/Origem", "")
            elif op == "🔀 Transferência (entrada)":
                origem, destino = h.get("Destino/Origem", ""), f
            else:
                continue
            detalhes = h.get("Detalhes") or ""
            m, sr, rc = _RE_PROTOCOLO.search(detalhes), _RE_SERIES.search(detalhes), _RE_RECEBEDOR.search(detalhes)
            protocolo = m.group(1) if m else ""
            data_hora = h.get("Data/Hora", "")
            chave = (protocolo or data_hora, h.get("Equipamento"), origem, destino)
            if chave in vistos:  # a mesma transferência aparece na origem e no destino
                continue
            vistos.add(chave)
            data, _, hora = data_hora.partition(" ")
            login = h.get("Usuário") or "—"
            nome_u = nomes_usuarios.get(login)
            linhas.append({
                "Protocolo": protocolo or "—", "Data": data, "Hora": hora,
                "Origem": origem, "Destino": destino, "Equipamento": h.get("Equipamento"),
                "Quantidade": h.get("Quantidade"), "Nº de série": sr.group(1) if sr else "",
                "Enviado por": f"{nome_u} ({login})" if nome_u else login,
                "Recebido por": rc.group(1).strip() if rc else "",
                "_data": data_hora,
            })
    df = pd.DataFrame(linhas, columns=COLUNAS_TRANSFERENCIAS + ["_data"])
    df["Quantidade"] = pd.to_numeric(df["Quantidade"], errors="coerce").astype("Int64")
    df["_data"] = pd.to_datetime(df["_data"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    return df.sort_values("_data", ascending=False, na_position="last").reset_index(drop=True)


# ============================================================ importação de planilha
_ALIAS = {
    "equipamento": {"equipamento", "nome", "produto", "item", "descricao"},
    "categoria": {"categoria", "tipo", "grupo"},
    "estoque": {"estoque", "quantidade", "qtd", "qtde", "estoque atual"},
    "alerta": {"alerta", "minimo", "estoque minimo", "alerta a partir de", "nivel de alerta"},
}


def _norm(texto):
    t = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in t if not unicodedata.combining(c)).strip().lower()


def ler_planilha(conteudo, nome_arquivo):
    ext = nome_arquivo.lower().rsplit(".", 1)[-1]
    try:
        if ext in ("xlsx", "xlsm", "xls"):
            df = pd.read_excel(io.BytesIO(conteudo), dtype=str)
        else:
            try:
                texto = conteudo.decode("utf-8-sig")
            except UnicodeDecodeError:
                texto = conteudo.decode("latin-1")
            df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    except ImportError as e:
        raise ValueError("Para ler Excel é preciso instalar o openpyxl (pip install openpyxl).") from e
    except Exception as e:  # noqa: BLE001 - qualquer falha de leitura vira mensagem amigável
        raise ValueError(f"Não consegui ler a planilha: {e}") from e
    if df.empty:
        raise ValueError("A planilha está vazia.")
    return df


def _inteiro(texto, padrao):
    if texto == "":
        return padrao
    try:
        v = float(texto.replace(",", "."))
    except ValueError:
        return None
    if v < 0 or v != int(v):
        return None
    return int(v)


def preparar_importacao(df):
    """Valida a planilha. Devolve (linhas_validas, erros)."""
    mapa = {}
    for col in df.columns:
        n = _norm(col)
        for campo, aliases in _ALIAS.items():
            if n in aliases and campo not in mapa:
                mapa[campo] = col
    if "equipamento" not in mapa:
        raise ValueError("Não encontrei a coluna com o nome do equipamento (use o título 'Equipamento').")

    def valor(row, campo):
        if campo not in mapa:
            return ""
        v = row[mapa[campo]]
        return "" if v is None or pd.isna(v) else str(v).strip()

    linhas, erros, vistos = [], [], {}
    for pos, (_, row) in enumerate(df.iterrows()):
        num = pos + 2  # linha da planilha (a 1 é o cabeçalho)
        if all((v is None or pd.isna(v) or not str(v).strip()) for v in row):
            continue
        nome = valor(row, "equipamento").upper()
        if not nome:
            erros.append(f"Linha {num}: sem nome de equipamento.")
            continue
        if nome in vistos:
            erros.append(f"Linha {num}: '{nome}' repetido (já aparece na linha {vistos[nome]}).")
            continue
        qtd = _inteiro(valor(row, "estoque"), 0)
        alerta = _inteiro(valor(row, "alerta"), None)
        if qtd is None:
            erros.append(f"Linha {num}: estoque inválido para '{nome}'.")
            continue
        if valor(row, "alerta") != "" and alerta is None:
            erros.append(f"Linha {num}: alerta inválido para '{nome}'.")
            continue
        vistos[nome] = num
        linhas.append({"nome": nome, "categoria": valor(row, "categoria"), "estoque": qtd, "alerta": alerta})
    return linhas, erros


def aplicar_importacao(dados, linhas, modo, usuario):
    produtos = dados["produtos"]
    resumo = {"novos": 0, "atualizados": 0, "pulados": 0, "avisos": []}
    for l in linhas:
        item = produtos.get(l["nome"])
        if item is None:
            novo = ItemTI(l["nome"], l["categoria"] or "Sem categoria", l["estoque"],
                          2 if l["alerta"] is None else l["alerta"])
            produtos[novo.nome] = novo
            registrar(dados["historico"], novo.nome, "🆕 Cadastro (importação)", usuario,
                      l["estoque"], 0, l["estoque"])
            resumo["novos"] += 1
            continue
        if item.controla_serie:
            resumo["avisos"].append(f"'{item.nome}' usa número de série e não pode ser alterado por planilha.")
            resumo["pulados"] += 1
        elif modo == MODO_PULAR:
            resumo["pulados"] += 1
        else:
            antes = item.estoque_atual
            novo = antes + l["estoque"] if modo == MODO_SOMAR else l["estoque"]
            if novo == antes:
                resumo["pulados"] += 1
                continue
            item.estoque_atual = novo
            registrar(dados["historico"], item.nome, f"📥 Importação ({modo})", usuario,
                      l["estoque"], antes, novo)
            resumo["atualizados"] += 1
    return resumo


MODELO_PLANILHA_CSV = (
    "Equipamento;Categoria;Estoque;Alerta\n"
    "MOUSE USB;Periféricos;10;3\n"
    "TECLADO ABNT2;Periféricos;8;3\n"
)


# ============================================================ tabelas e relatórios
def df_inventario(produtos):
    colunas = ["Equipamento", "Categoria", "Estoque Atual", "Alerta a partir de", "Status", "Nº de série"]
    linhas = [
        {
            "Equipamento": i.nome,
            "Categoria": i.categoria,
            "Estoque Atual": i.estoque_atual,
            "Alerta a partir de": i.estoque_minimo,
            "Status": i.status,
            "Nº de série": "Sim" if i.controla_serie else "—",
        }
        for i in produtos.values()
    ]
    return pd.DataFrame(linhas, columns=colunas)


def df_unidades(produtos):
    """Uma linha por número de série (itens controlados por série)."""
    linhas = [
        {
            "Equipamento": i.nome,
            "Nº de série / patrimônio": s,
            "Situação": u.get("situacao", ""),
            "Destino": u.get("destino", ""),
            "Data": u.get("data", ""),
        }
        for i in produtos.values() if i.controla_serie
        for s, u in sorted(i.unidades.items())
    ]
    return pd.DataFrame(linhas, columns=["Equipamento", "Nº de série / patrimônio", "Situação", "Destino", "Data"])


def resumo_filiais(filiais, nomes):
    linhas = []
    for n in nomes:
        itens = list(filiais[n]["produtos"].values())
        linhas.append(
            {
                "Filial": n,
                "SKUs": len(itens),
                "Unidades": sum(i.estoque_atual for i in itens),
                "Zerados": sum(1 for i in itens if i.status == config.STATUS_CRITICO),
                "Em alerta": sum(1 for i in itens if i.status == config.STATUS_ALERTA),
            }
        )
    return pd.DataFrame(linhas, columns=["Filial", "SKUs", "Unidades", "Zerados", "Em alerta"])


def tabela_por_filial(filiais, nomes):
    linhas = [
        {"Filial": n, "Equipamento": i.nome, "Estoque Atual": i.estoque_atual}
        for n in nomes for i in filiais[n]["produtos"].values()
    ]
    if not linhas:
        return pd.DataFrame()
    tabela = pd.DataFrame(linhas).pivot_table(
        index="Equipamento", columns="Filial", values="Estoque Atual", aggfunc="sum", fill_value=0
    )
    tabela["Total"] = tabela.sum(axis=1)
    return tabela.reset_index()


def itens_para_repor(filiais, nomes, multiplicador=2):
    """Itens zerados ou em alerta. Sugestão = quanto falta para ter 'multiplicador' x o nível de alerta."""
    linhas = []
    for n in nomes:
        for i in filiais[n]["produtos"].values():
            if i.status == config.STATUS_OK:
                continue
            meta = max(i.estoque_minimo * multiplicador, i.estoque_minimo + 1)
            linhas.append(
                {
                    "Filial": n,
                    "Equipamento": i.nome,
                    "Categoria": i.categoria,
                    "Estoque Atual": i.estoque_atual,
                    "Alerta a partir de": i.estoque_minimo,
                    "Situação": i.status,
                    "Sugestão de compra": max(meta - i.estoque_atual, 1),
                }
            )
    ordem = {config.STATUS_CRITICO: 0, config.STATUS_ALERTA: 1}
    linhas.sort(key=lambda r: (ordem[r["Situação"]], r["Filial"], r["Equipamento"]))
    return pd.DataFrame(
        linhas,
        columns=["Filial", "Equipamento", "Categoria", "Estoque Atual", "Alerta a partir de",
                 "Situação", "Sugestão de compra"],
    )


def texto_reposicao(df):
    """Texto pronto para colar no WhatsApp ou e-mail."""
    partes = [f"Reposição de estoque de T.I. - {datetime.now().strftime('%d/%m/%Y')}"]
    for filial, grupo in df.groupby("Filial", sort=False):
        partes.append(f"\n*{filial}*")
        for _, r in grupo.iterrows():
            partes.append(
                f"- {r['Equipamento']}: estoque {r['Estoque Atual']} "
                f"(alerta {r['Alerta a partir de']}) -> comprar {r['Sugestão de compra']}"
            )
    return "\n".join(partes)


# ============================================================ histórico e análises
def historico_df(historico):
    df = pd.DataFrame(historico, columns=COLUNAS_HISTORICO)
    for c in ["Quantidade", "Estoque Anterior", "Estoque Final"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c, vazio in [("Usuário", "—"), ("Destino/Origem", ""), ("Detalhes", "")]:
        df[c] = df[c].fillna(vazio)
    df["_data"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    return df


def filtrar_historico(df, inicio=None, fim=None, equipamentos=None, operacoes=None, usuarios=None):
    if inicio is not None:
        df = df[df["_data"].dt.date >= inicio]
    if fim is not None:
        df = df[df["_data"].dt.date <= fim]
    if equipamentos:
        df = df[df["Equipamento"].isin(equipamentos)]
    if operacoes:
        df = df[df["Operação"].isin(operacoes)]
    if usuarios:
        df = df[df["Usuário"].isin(usuarios)]
    return df


def movimentacao_por_mes(historico):
    """DataFrame indexado por mês (AAAA-MM) com colunas Entradas e Saídas (unidades)."""
    df = historico_df(historico).dropna(subset=["_data", "Quantidade"])
    df = df.assign(Mes=df["_data"].dt.strftime("%Y-%m"))
    ent = df[df["Operação"].str.contains("📥 Entrada", regex=False)].groupby("Mes")["Quantidade"].sum()
    sai = df[df["Operação"].str.contains("📤 Saída", regex=False)].groupby("Mes")["Quantidade"].sum()
    out = pd.DataFrame({"Entradas": ent, "Saídas": sai}).fillna(0).astype(int).sort_index()
    out.index.name = "Mês"
    return out


def top_saidas(historico, n=10):
    df = historico_df(historico).dropna(subset=["Quantidade"])
    df = df[df["Operação"].str.contains("📤 Saída", regex=False)]
    serie = df.groupby("Equipamento")["Quantidade"].sum().sort_values(ascending=False).head(n)
    return serie.astype(int)

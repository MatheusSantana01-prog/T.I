"""Página: Transferir produtos entre filiais, com comprovante e relatório."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from nucleo import config, relatorios, servicos

from . import ui

MODO_NOVA = "🔀 Nova transferência"
MODO_RELATORIO = "📑 Relatório de transferências"
OUTRA_PESSOA = "✍️ Outra pessoa (digitar o nome)"


def mostrar(ctx):
    destinos = [n for n in ctx.filiais_visiveis if n != ctx.filial_atual]
    pode_transferir = ctx.pode_editar and bool(destinos)
    modos = [MODO_NOVA, MODO_RELATORIO] if pode_transferir else [MODO_RELATORIO]
    if st.session_state.get("tr_modo") not in modos:
        st.session_state.pop("tr_modo", None)
    modo = modos[0]
    if len(modos) > 1:
        modo = st.radio("Transferências", modos, horizontal=True, key="tr_modo", label_visibility="collapsed")

    if modo == MODO_NOVA:
        _nova(ctx, destinos)
    else:
        if ctx.pode_editar and not destinos:
            st.info("Para fazer transferências é preciso ter acesso a pelo menos uma outra filial.")
        _relatorio(ctx)


# ====================================================================== nova transferência
def _nova(ctx, destinos):
    comprovante = st.session_state.get("tr_comprovante")
    if comprovante:
        _mostrar_comprovante(comprovante)
        st.divider()

    nomes = sorted(ctx.produtos)
    if not nomes:
        st.info("Esta filial ainda não tem produtos para transferir.")
        return

    st.caption(f"Origem: **{ctx.filial_atual}** (para transferir de outra filial, troque a filial na barra lateral).")
    ui.sincronizar_selecao("tr_dest", destinos)
    destino = st.selectbox("Filial de destino:", destinos, key="tr_dest")

    # a lista recomeça se a origem ou o destino mudarem
    lista = st.session_state.get("tr_lista")
    if not lista or lista["origem"] != ctx.filial_atual or lista["destino"] != destino:
        lista = {"origem": ctx.filial_atual, "destino": destino, "itens": []}
        st.session_state["tr_lista"] = lista
    itens = lista["itens"]

    # ---- 1. escolher produtos
    st.markdown("**1. Escolha os produtos e adicione à lista**")
    ui.sincronizar_selecao("tr_equip", nomes)
    equipamento = st.selectbox("Equipamento:", nomes, key="tr_equip")
    item = ctx.produtos[equipamento]
    na_lista = next((i for i in itens if i["equipamento"] == equipamento), None)
    k = f"{ctx.filial_atual}_{equipamento}_{len(itens)}"  # muda a cada item adicionado: campos limpam
    pode_add, qtd, series_sel = False, 0, []

    if item.controla_serie:
        ja = set(na_lista["series"]) if na_lista else set()
        disponiveis = [s for s in item.series_em_estoque() if s not in ja]
        if not disponiveis:
            st.info("Todas as unidades deste item em estoque já estão na lista (ou não há nenhuma).")
        else:
            series_sel = st.multiselect("Quais unidades serão transferidas?", disponiveis, key=f"tr_series_{k}")
            pode_add = bool(series_sel)
    else:
        restante = item.estoque_atual - (na_lista["quantidade"] if na_lista else 0)
        if restante < 1:
            st.info("Sem estoque disponível deste item (ou todo o estoque já está na lista).")
        else:
            qtd = st.number_input("Quantidade:", min_value=1, max_value=restante, value=1, step=1,
                                  key=f"tr_qtd_{k}_{restante}")
            pode_add = True

    if st.button("➕ Adicionar à lista", key="btn_tr_add", disabled=not pode_add):
        if item.controla_serie:
            if na_lista:
                na_lista["series"] = na_lista["series"] + [s for s in series_sel if s not in na_lista["series"]]
                na_lista["quantidade"] = len(na_lista["series"])
            else:
                itens.append({"equipamento": equipamento, "quantidade": len(series_sel), "series": list(series_sel)})
        elif na_lista:
            na_lista["quantidade"] += int(qtd)
        else:
            itens.append({"equipamento": equipamento, "quantidade": int(qtd), "series": []})
        st.rerun()

    # ---- 2. lista e confirmação
    st.markdown(f"**2. Lista de transferência: {ctx.filial_atual} → {destino}**")
    if not itens:
        st.info("Nenhum produto na lista ainda.")
        return
    ui.mostrar_tabela(pd.DataFrame([
        {"Equipamento": i["equipamento"], "Quantidade": i["quantidade"], "Nº de série": ", ".join(i["series"]) or "—"}
        for i in itens
    ]))
    st.caption(f"Total: {len(itens)} produto(s), {sum(i['quantidade'] for i in itens)} unidade(s).")

    c1, c2 = st.columns([2, 1])
    remover = c1.selectbox("Remover da lista:", [i["equipamento"] for i in itens], key=f"tr_rem_{len(itens)}")
    if c2.button("🗑️ Remover", key="btn_tr_rem"):
        itens[:] = [i for i in itens if i["equipamento"] != remover]
        st.rerun()

    st.markdown("**3. Quem vai receber no destino**")
    rec_login, rec_nome = _escolher_recebedor(ctx, destino)

    b1, b2 = st.columns(2)
    if b1.button("✅ Confirmar transferência", key="btn_tr_confirmar"):
        if not rec_nome:
            st.error("Informe quem vai receber a transferência.")
        else:
            ok, msg, comp = servicos.transferir_lote(ctx.filiais, ctx.filial_atual, destino, itens,
                                                     ctx.usuario_id, ctx.usuario["nome"], rec_login, rec_nome)
            if ok:
                ctx.salvar()
                st.session_state["tr_comprovante"] = comp
                st.session_state.pop("tr_lista", None)
                ui.avisar("sucesso", msg)
                st.rerun()
            else:
                st.error(msg)
    if b2.button("🧹 Limpar lista", key="btn_tr_limpar"):
        itens.clear()
        st.rerun()


def _escolher_recebedor(ctx, destino):
    """Devolve (login, nome) de quem vai receber; o nome aparece no campo de assinatura do PDF."""
    rotulos = {}
    for login, u in sorted(ctx.usuarios.items()):
        if u["ativo"] and (u["perfil"] == config.PERFIL_ADMIN or destino in u["filiais"]):
            rotulos[f"{u['nome']} ({login})"] = (login, u["nome"])
    opcoes = list(rotulos) + [OUTRA_PESSOA]
    chave = f"tr_receb_{destino}"
    ui.sincronizar_selecao(chave, opcoes)
    escolha = st.selectbox("Quem vai receber no destino:", opcoes, key=chave)
    if escolha == OUTRA_PESSOA:
        nome = st.text_input("Nome de quem vai receber:", key=f"tr_receb_nome_{destino}").strip()
        return "", nome
    return rotulos[escolha]


def _mostrar_comprovante(c):
    data, _, hora = c["data_hora"].partition(" ")
    total = sum(i["quantidade"] for i in c["itens"])
    st.markdown(
        f"""
        <div class="card-info">
            <h3 style='margin-top:0; color:white;'>🧾 Comprovante de transferência</h3>
            <p><b>Protocolo:</b> {ui.esc(c['protocolo'])}</p>
            <p><b>Data:</b> {data} &nbsp;&nbsp; <b>Hora:</b> {hora}</p>
            <p><b>Saindo de:</b> {ui.esc(c['origem'])} &nbsp;→&nbsp; <b>Indo para:</b> {ui.esc(c['destino'])}</p>
            <p><b>Enviado por:</b> {ui.esc(c['usuario_nome'])} ({ui.esc(c['usuario'])})</p>
            <p><b>Quem vai receber:</b> {ui.esc(c.get('recebedor') or '-')}</p>
            <p><b>Total:</b> {len(c['itens'])} produto(s), {total} unidade(s)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ui.mostrar_tabela(pd.DataFrame([
        {"Produto": i["equipamento"], "Categoria": i["categoria"], "Quantidade": i["quantidade"],
         "Nº de série": ", ".join(i["series"]) or "—"} for i in c["itens"]
    ]))
    b1, b2, b3 = st.columns(3)
    try:
        b1.download_button("⬇️ Baixar comprovante (PDF)", relatorios.pdf_comprovante(c),
                           file_name=f"comprovante_{c['protocolo']}.pdf", mime="application/pdf",
                           key="dl_comprovante_pdf")
    except ImportError:
        b1.caption("Para gerar PDF instale o reportlab (pip install reportlab).")
    tabela = pd.DataFrame([
        {"Protocolo": c["protocolo"], "Data": data, "Hora": hora, "Origem": c["origem"], "Destino": c["destino"],
         "Produto": i["equipamento"], "Quantidade": i["quantidade"], "Nº de série": ", ".join(i["series"]),
         "Enviado por": f"{c['usuario_nome']} ({c['usuario']})", "Recebido por": c.get("recebedor", "")}
        for i in c["itens"]
    ])
    b2.download_button("⬇️ Baixar (CSV)", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"comprovante_{c['protocolo']}.csv", mime="text/csv", key="dl_comprovante_csv")
    if b3.button("✖️ Fechar comprovante", key="btn_fechar_comprovante"):
        st.session_state.pop("tr_comprovante", None)
        st.rerun()


# ====================================================================== relatório
def _relatorio(ctx):
    nomes_usuarios = {k: v["nome"] for k, v in ctx.usuarios.items()}
    df = servicos.df_transferencias(ctx.filiais, ctx.filiais_visiveis, nomes_usuarios)
    st.subheader("📑 Relatório de transferências")
    if df.empty:
        st.info("Nenhuma transferência registrada ainda.")
        return

    with st.expander("🔎 Filtros", expanded=True):
        inicio = fim = None
        if st.checkbox("Filtrar por período", key="tr_rel_usar_periodo"):
            d1, d2 = st.columns(2)
            inicio = d1.date_input("De:", value=date.today() - timedelta(days=30), key="tr_rel_de")
            fim = d2.date_input("Até:", value=date.today(), key="tr_rel_ate")
        opcoes = {
            "origem": sorted(df["Origem"].dropna().unique()),
            "destino": sorted(df["Destino"].dropna().unique()),
            "equip": sorted(df["Equipamento"].dropna().unique()),
        }
        for nome, ops in opcoes.items():
            ui.limpar_selecao_invalida(f"tr_rel_{nome}", ops)
        m1, m2, m3 = st.columns(3)
        f_origem = m1.multiselect("Origem:", opcoes["origem"], key="tr_rel_origem")
        f_destino = m2.multiselect("Destino:", opcoes["destino"], key="tr_rel_destino")
        f_equip = m3.multiselect("Equipamento:", opcoes["equip"], key="tr_rel_equip")

    if inicio is not None:
        df = df[df["_data"].dt.date >= inicio]
    if fim is not None:
        df = df[df["_data"].dt.date <= fim]
    if f_origem:
        df = df[df["Origem"].isin(f_origem)]
    if f_destino:
        df = df[df["Destino"].isin(f_destino)]
    if f_equip:
        df = df[df["Equipamento"].isin(f_equip)]

    tabela = df.drop(columns="_data")
    total = int(tabela["Quantidade"].fillna(0).sum()) if len(tabela) else 0
    st.caption(f"{len(tabela)} registro(s) — {total} unidade(s) transferida(s).")
    if tabela.empty:
        st.info("Nenhuma transferência encontrada com esses filtros.")
        return
    ui.mostrar_tabela(tabela)

    partes = []
    if inicio is not None:
        partes.append(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}")
    for rotulo, valores in (("Origem", f_origem), ("Destino", f_destino), ("Equipamento", f_equip)):
        if valores:
            partes.append(f"{rotulo}: {', '.join(valores)}")
    d1, d2, _ = st.columns(3)
    try:
        d1.download_button("⬇️ Baixar relatório (PDF)",
                           relatorios.pdf_relatorio_transferencias(tabela, " | ".join(partes)),
                           file_name="relatorio_transferencias.pdf", mime="application/pdf", key="dl_rel_pdf")
    except ImportError:
        d1.caption("Para gerar PDF instale o reportlab (pip install reportlab).")
    d2.download_button("⬇️ Baixar relatório (CSV)", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name="relatorio_transferencias.csv", mime="text/csv", key="dl_rel_csv")

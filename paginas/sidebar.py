"""Barra lateral: usuário, filial, gestão de filiais (admin), filtros e backup."""
import streamlit as st

from nucleo import armazenamento, config, seguranca, servicos
from nucleo.modelos import ItemTI

from . import login, ui


def construir(ctx):
    with st.sidebar:
        st.markdown("<h2 style='color:#3b82f6;'>⚙️ Central TI</h2>", unsafe_allow_html=True)
        st.caption(f"👤 {ctx.usuario['nome']} · {ctx.usuario['perfil']}")
        st.button("🚪 Sair", on_click=login.sair, key="btn_sair")
        _minha_conta(ctx)
        st.divider()

        ui.sincronizar_selecao("filial_sel", ctx.filiais_visiveis)
        ctx.filial_atual = st.selectbox("🏢 Filial:", ctx.filiais_visiveis, key="filial_sel")

        if ctx.eh_admin:
            _gerir_filiais(ctx)

        st.divider()
        ctx.df_atual = servicos.df_inventario(ctx.produtos)
        categorias = ["Todas"] + sorted(ctx.df_atual["Categoria"].unique().tolist())
        if st.session_state.get("filtro_categoria") not in categorias:
            st.session_state.pop("filtro_categoria", None)
        ctx.categoria_sel = st.selectbox("Filtrar Categoria:", categorias, key="filtro_categoria")
        ctx.status_sel = st.selectbox(
            "Filtrar Situação:",
            ["Todos", config.STATUS_OK, config.STATUS_ALERTA, config.STATUS_CRITICO],
            key="filtro_status",
        )
        st.caption("Filtros aplicados ao Inventário.")

        if ctx.eh_admin:
            _backup()


def _minha_conta(ctx):
    u = ctx.usuario
    with st.expander("🔑 Minha conta"):
        with st.form("form_minha_senha", clear_on_submit=True):
            senha_atual = st.text_input("Senha atual:", type="password")
            nova1 = st.text_input("Nova senha:", type="password")
            nova2 = st.text_input("Repita a nova senha:", type="password")
            trocar = st.form_submit_button("💾 Trocar senha")
        if trocar:
            if not seguranca.conferir_senha(senha_atual, u["salt"], u["hash"]):
                st.error("Senha atual incorreta.")
            elif len(nova1) < config.MIN_SENHA:
                st.error(f"A nova senha precisa ter pelo menos {config.MIN_SENHA} caracteres.")
            elif nova1 != nova2:
                st.error("As senhas não conferem.")
            else:
                u["salt"], u["hash"] = seguranca.gerar_hash(nova1)
                ctx.salvar_usuarios()
                st.success("Senha alterada!")


def _gerir_filiais(ctx):
    filiais, atual = ctx.filiais, ctx.filial_atual
    with st.expander("➕ Gerir filiais"):
        with st.form("form_nova_filial", clear_on_submit=True):
            nome_nova = st.text_input("Nome da nova filial:", placeholder="Ex: Filial Centro")
            copiar_de = st.selectbox("Copiar a lista de produtos de:", ["Começar vazia"] + list(filiais))
            criar = st.form_submit_button("➕ Criar filial")
        st.caption("Ao copiar, os produtos entram na nova filial com estoque zerado.")

        if criar:
            nome_nova = nome_nova.strip()
            if not nome_nova:
                st.error("Informe o nome da filial.")
            elif nome_nova.lower() in [n.lower() for n in filiais]:
                st.error("Já existe uma filial com esse nome.")
            else:
                novos = {}
                if copiar_de in filiais:
                    for i in filiais[copiar_de]["produtos"].values():
                        novos[i.nome] = ItemTI(i.nome, i.categoria, 0, i.estoque_minimo, i.controla_serie)
                filiais[nome_nova] = {"produtos": novos, "historico": []}
                ctx.salvar()
                st.session_state["filial_sel_pendente"] = nome_nova
                ui.avisar("sucesso", f"Filial '{nome_nova}' criada!")
                st.rerun()

        st.divider()
        with st.form(f"form_renomear_{atual}"):
            novo_nome = st.text_input("Renomear filial atual:", value=atual)
            renomear = st.form_submit_button("💾 Renomear")
        if renomear:
            novo = novo_nome.strip()
            outros = [n.lower() for n in filiais if n != atual]
            if not novo:
                st.error("O nome não pode ficar vazio.")
            elif novo.lower() in outros:
                st.error("Já existe uma filial com esse nome.")
            elif novo != atual:
                renomeadas = {(novo if n == atual else n): d for n, d in filiais.items()}
                filiais.clear()
                filiais.update(renomeadas)
                ctx.salvar()
                for u in ctx.usuarios.values():
                    u["filiais"] = [novo if f == atual else f for f in u["filiais"]]
                ctx.salvar_usuarios()
                st.session_state["filial_sel_pendente"] = novo
                ui.avisar("sucesso", f"Filial renomeada para '{novo}'.")
                st.rerun()

        st.divider()
        if len(filiais) > 1:
            conf = st.checkbox(f"Confirmo excluir '{atual}' e todo o estoque dela", key=f"conf_del_filial_{atual}")
            if st.button("🗑️ Excluir filial", disabled=not conf, key="btn_del_filial"):
                del filiais[atual]
                ctx.salvar()
                for u in ctx.usuarios.values():
                    u["filiais"] = [f for f in u["filiais"] if f != atual]
                ctx.salvar_usuarios()
                ui.avisar("aviso", f"Filial '{atual}' excluída.")
                st.rerun()
        else:
            st.caption("É preciso manter pelo menos uma filial.")


def _backup():
    with st.expander("💾 Backup"):
        st.caption(
            "O sistema guarda uma cópia automática por dia na pasta 'backups' "
            f"(últimos {config.DIAS_BACKUP} dias). Há {len(armazenamento.listar_backups())} arquivo(s) lá."
        )
        st.download_button(
            "⬇️ Baixar backup agora (.zip)",
            data=armazenamento.gerar_zip_backup(),
            file_name="backup_ti_stock.zip",
            mime="application/zip",
            key="btn_baixar_backup",
        )

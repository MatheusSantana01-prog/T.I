"""Página: Usuários e permissões (somente administrador)."""
import pandas as pd
import streamlit as st

from nucleo import config, seguranca

from . import ui


def mostrar(ctx):
    if not ctx.eh_admin:
        st.error("Apenas administradores podem gerir usuários.")
        return
    usuarios, filiais = ctx.usuarios, ctx.filiais
    ver = st.session_state.get("ver_form_user", 0)  # troca as chaves para limpar os formulários

    st.subheader("👥 Usuários cadastrados")
    ui.mostrar_tabela(
        pd.DataFrame(
            [
                {
                    "Usuário": login,
                    "Nome": u["nome"],
                    "Perfil": u["perfil"],
                    "Filiais": "Todas" if u["perfil"] == config.PERFIL_ADMIN else (", ".join(u["filiais"]) or "—"),
                    "Situação": "✅ Ativo" if u["ativo"] else "⛔ Inativo",
                }
                for login, u in usuarios.items()
            ]
        )
    )
    st.caption(
        "Administrador: acesso total. Operador: vê e movimenta o estoque, transfere entre as filiais liberadas "
        "e cadastra/edita produtos. Somente leitura: apenas consulta as filiais liberadas."
    )

    col_novo, col_edit = st.columns(2, gap="large")

    # ---------------------------------------------------------- novo usuário
    with col_novo:
        st.subheader("➕ Novo usuário")
        with st.form("form_novo_usuario"):
            n_nome = st.text_input("Nome completo:", key=f"nu_nome_{ver}")
            n_login = st.text_input("Usuário (login):", placeholder="ex: maria.embu", key=f"nu_login_{ver}")
            n_perfil = st.selectbox("Perfil:", config.PERFIS, index=1, key=f"nu_perfil_{ver}")
            n_filiais = st.multiselect("Filiais liberadas (não vale para administrador):",
                                       list(filiais), key=f"nu_fil_{ver}")
            n_senha = st.text_input("Senha:", type="password", key=f"nu_senha_{ver}")
            n_senha2 = st.text_input("Repita a senha:", type="password", key=f"nu_senha2_{ver}")
            criar = st.form_submit_button("➕ Criar usuário")

        if criar:
            login_novo = n_login.strip().lower()
            if not n_nome.strip():
                st.error("Informe o nome.")
            elif not seguranca.login_valido(login_novo):
                st.error("Usuário: 3 a 30 caracteres, só letras minúsculas, números, ponto, _ ou -.")
            elif login_novo in usuarios:
                st.error("Esse usuário já existe.")
            elif n_perfil != config.PERFIL_ADMIN and not n_filiais:
                st.error("Escolha pelo menos uma filial para este usuário.")
            elif len(n_senha) < config.MIN_SENHA:
                st.error(f"A senha precisa ter pelo menos {config.MIN_SENHA} caracteres.")
            elif n_senha != n_senha2:
                st.error("As senhas não conferem.")
            else:
                usuarios[login_novo] = seguranca.novo_usuario(n_nome, n_perfil, n_filiais, n_senha)
                ctx.salvar_usuarios()
                st.session_state["ver_form_user"] = ver + 1
                ui.avisar("sucesso", f"Usuário '{login_novo}' criado!")
                st.rerun()

    # ---------------------------------------------------------- editar / excluir
    with col_edit:
        st.subheader("✏️ Editar usuário")
        logins = sorted(usuarios)
        ui.sincronizar_selecao("edit_user", logins)
        sel = st.selectbox("Usuário:", logins, key="edit_user")
        u = usuarios[sel]
        outros_admins = [k for k, x in usuarios.items()
                         if k != sel and x["perfil"] == config.PERFIL_ADMIN and x["ativo"]]

        with st.form(f"form_edit_user_{sel}"):
            e_nome = st.text_input("Nome:", value=u["nome"], key=f"eu_nome_{sel}_{ver}")
            e_perfil = st.selectbox("Perfil:", config.PERFIS, index=config.PERFIS.index(u["perfil"]),
                                    key=f"eu_perfil_{sel}_{ver}")
            e_filiais = st.multiselect("Filiais liberadas (não vale para administrador):", list(filiais),
                                       default=[f for f in u["filiais"] if f in filiais],
                                       key=f"eu_fil_{sel}_{ver}")
            e_ativo = st.checkbox("Usuário ativo", value=u["ativo"], key=f"eu_ativo_{sel}_{ver}")
            e_senha = st.text_input("Nova senha (deixe vazio para manter):", type="password",
                                    key=f"eu_senha_{sel}_{ver}")
            salvar = st.form_submit_button("💾 Salvar usuário")

        if salvar:
            if not e_nome.strip():
                st.error("O nome não pode ficar vazio.")
            elif e_senha and len(e_senha) < config.MIN_SENHA:
                st.error(f"A senha precisa ter pelo menos {config.MIN_SENHA} caracteres.")
            elif e_perfil != config.PERFIL_ADMIN and not e_filiais:
                st.error("Escolha pelo menos uma filial para este usuário.")
            elif (e_perfil != config.PERFIL_ADMIN or not e_ativo) and not outros_admins:
                st.error("Precisa existir pelo menos um administrador ativo.")
            else:
                u["nome"] = e_nome.strip()
                u["perfil"] = e_perfil
                u["filiais"] = [] if e_perfil == config.PERFIL_ADMIN else list(e_filiais)
                u["ativo"] = e_ativo
                u["falhas"] = 0
                u["bloqueado_ate"] = None
                if e_senha:
                    u["salt"], u["hash"] = seguranca.gerar_hash(e_senha)
                ctx.salvar_usuarios()
                st.session_state["ver_form_user"] = ver + 1
                ui.avisar("sucesso", f"Usuário '{sel}' atualizado!")
                st.rerun()

        st.divider()
        conf = st.checkbox(f"Confirmo excluir o usuário '{sel}'", key=f"conf_del_user_{sel}")
        if st.button("🗑️ Excluir usuário", disabled=not conf, key="btn_del_user"):
            if sel == ctx.usuario_id:
                st.error("Você não pode excluir o seu próprio usuário.")
            elif u["perfil"] == config.PERFIL_ADMIN and not outros_admins:
                st.error("Precisa existir pelo menos um administrador ativo.")
            else:
                del usuarios[sel]
                ctx.salvar_usuarios()
                ui.avisar("aviso", f"Usuário '{sel}' excluído.")
                st.rerun()

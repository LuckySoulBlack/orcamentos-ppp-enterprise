GUIA DE INSTALACAO E ATUALIZACAO - CLIENTE

Aplicativos:
- Orcamentos PPP: sistema administrativo.
- OS PPP: sistema operacional de ordens de servico.

Pasta padrao:
C:\Orcamentos_PPP

Executaveis:
C:\Orcamentos_PPP\01_Orcamentos_PPP\Orcamentos_PPP.exe
C:\Orcamentos_PPP\02_OS_PPP\OS_PPP.exe

Atalhos:
- Orcamentos PPP.lnk deve abrir Orcamentos_PPP.exe.
- OS PPP.lnk deve abrir OS_PPP.exe.

Login de recuperacao:
- Usuario: admin
- Senha: admin
- E-mail alternativo: admin@local

Banco de dados:
- O arquivo principal e app.db.
- Faca backup antes de qualquer atualizacao.
- Nunca substitua app.db do cliente sem confirmar que a intencao e restaurar outro banco.

Google Drive:
- Instale o Google Drive no computador quando houver uso compartilhado.
- Configure o app para apontar para a pasta local sincronizada, nao para o link web.
- Exemplo correto: G:\Meu Drive\Backup Orcamentos PP
- Exemplo incorreto para pasta sincronizada: https://drive.google.com/...

Atualizacao somente de layout:
- Feche o aplicativo.
- Substitua apenas o EXE correspondente.
- Mantenha a pasta _internal e o app.db.

Atualizacao com funcao nova, tela nova, relatorio novo ou banco:
- Feche os aplicativos.
- Faca backup de app.db, anexos, gerados e backups.
- Troque a pasta completa do aplicativo.
- Recoloque ou preserve o app.db real do cliente.
- Abra e teste login, configuracoes, lista de usuarios e tela principal.

Checklist final:
1. Orcamentos PPP abre.
2. OS PPP abre.
3. Login admin/admin funciona no Orcamentos PPP.
4. Usuario autorizado consegue entrar no OS PPP.
5. Configuracoes mostra banco correto.
6. Relatorios geram PDF/Word/Excel.
7. Atalhos da area de trabalho apontam para C:\Orcamentos_PPP.

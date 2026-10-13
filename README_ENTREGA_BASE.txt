ORCAMENTOS PPP / OS PPP - ENTREGA ORGANIZADA

Data da revisao: 16/07/2026

Esta entrega trabalha com dois aplicativos separados:

1. Orcamentos PPP
   Sistema administrativo para orcamentos, clientes, contratos, usuarios, permissoes, configuracoes, relatorios e aprovacao/transformacao de OS.

2. OS PPP
   Sistema operacional para criacao, execucao e documentacao de ordens de servico, com fotos, etapas, anexos, mapa e kanban.

INSTALACAO PADRAO

A instalacao local padrao fica em:
C:\Orcamentos_PPP

Executaveis principais:
C:\Orcamentos_PPP\01_Orcamentos_PPP\Orcamentos_PPP.exe
C:\Orcamentos_PPP\02_OS_PPP\OS_PPP.exe

Os atalhos da area de trabalho devem apontar para esses executaveis.

LOGIN DE RECUPERACAO

Usuario: admin
Senha: admin

Tambem pode entrar com:
E-mail: admin@local
Senha: admin

BANCO DE DADOS

O banco principal chama app.db.

Na instalacao local padrao ele fica em:
C:\Orcamentos_PPP\01_Orcamentos_PPP\_internal\data\app.db

O OS PPP tambem recebe uma copia local para operar com a mesma base quando o pacote e instalado.

Se for usar Google Drive ou pasta de rede, configure pelo app Orcamentos PPP em:
Configuracoes > Banco de dados e anexos compartilhados

Importante:
- Em "Pasta Drive sincronizada", selecione a pasta local do computador, por exemplo G:\Meu Drive\Backup Orcamentos PP.
- Nao cole link web do Google Drive no campo de pasta sincronizada.
- Todos os computadores que precisarem compartilhar dados devem apontar para a mesma pasta local sincronizada.
- Nao substitua app.db do cliente sem backup.

REGRA DE ATUALIZACAO

Trocar somente o EXE:
- Use apenas para correcao visual, texto, layout e pequenos ajustes que nao mudam banco, telas novas, relatorios novos ou dependencias.
- Pode substituir somente Orcamentos_PPP.exe ou OS_PPP.exe, mantendo a pasta _internal.

Trocar a pasta completa:
- Use quando houver tela nova, funcao nova, relatorio novo, dependencia nova, alteracao de estrutura de banco ou recurso dentro de _internal.
- Antes de trocar, faca backup de app.db, anexos, gerados e backups.
- Preserve o app.db real do cliente, exceto quando a intencao for restaurar/importar outro banco.

PACOTE PARA PENDRIVE

Use a pasta:
Pacote_Instalacao_Pendrive_Orcamentos_PPP_20260714

Para instalar em cliente:
1. Copie a pasta do pacote para o computador.
2. Preferencialmente instale em C:\Orcamentos_PPP.
3. Crie ou atualize os atalhos da area de trabalho.
4. Abra Orcamentos PPP e teste admin / admin.
5. Abra OS PPP e teste usuario autorizado.
6. Confira em Configuracoes se o banco esta apontando para a pasta correta.

NAO EXECUTAR DIRETO DO PENDRIVE

O pendrive serve para transporte do pacote.
Para uso diario, copie para o computador do cliente.

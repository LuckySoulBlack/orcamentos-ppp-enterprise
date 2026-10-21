# Orçamentos PPP Enterprise

Sistema desktop para gestão de orçamentos e ordens de serviço de contratos PPP, desenvolvido em Python com interface PySide6 e banco SQLite.

## Aplicativos e recursos

- **Orçamentos PPP:** clientes, contratos e aditivos, segmentos, importação SINAPI, elaboração de orçamentos, relatórios, usuários e permissões.
- **OS PPP:** criação e acompanhamento de ordens de serviço, etapas, anexos, fotografias, mapa e kanban.
- **Portal do Executor:** página HTML para coleta de registros de execução e exportação de arquivos.
- Geração de documentos em PDF, Word e Excel.

## Estrutura

- `src/app/main.py`: aplicativo administrativo.
- `src/app/main_os.py`: aplicativo operacional.
- `src/app/core/`: banco, sessão e componentes comuns.
- `src/app/services/`: regras e geração de documentos.
- `src/app/repositories/`: acesso aos dados.
- `src/app/views/` e `src/app/widgets/`: interface.
- `src/app/assets/`: recursos visuais distribuídos com o código.
- `Portal_Executor_Web/index.html`: portal do executor.
- `src/*.spec`: configuração de empacotamento com PyInstaller.

## Baixar os executáveis para Windows

A [release 2.2.0 — compilação de 23/07/2026](https://github.com/LuckySoulBlack/orcamentos-ppp-enterprise/releases/tag/v2.2.0-build.20260723) disponibiliza os executáveis mais recentes encontrados na distribuição local:

- `Orcamentos_PPP-2.2.0-windows.zip`: aplicativo administrativo, com `Orcamentos_PPP.exe`.
- `OS_PPP-2.2.0-windows.zip`: aplicativo operacional, com `OS_PPP.exe`.
- `SHA256SUMS.txt`: hashes para conferir a integridade dos downloads.

Extraia todo o ZIP em uma pasta e abra o executável. Mantenha a pasta `_internal` ao lado do `.exe`, pois ela contém as bibliotecas necessárias. Não é necessário instalar Python para usar esses pacotes.

Os pacotes preservam os binários compilados em 23/07/2026 e não incluem banco de dados, registros operacionais, configuração local nem imagens particulares da empresa. Não são uma nova compilação do código. A integridade dos ZIPs e a correspondência dos executáveis com os originais foram verificadas; não foi realizado teste funcional da interface nesta publicação.

## Execução no Windows

Requer Python 3.12 ou 3.13. A cópia local foi desenvolvida com Python 3.13; as dependências estão em `src/requirements.txt`.

No PowerShell, a partir da raiz do repositório:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r src\requirements.txt
.\.venv\Scripts\python.exe src\app\main.py
```

Para abrir o módulo operacional:

```powershell
.\.venv\Scripts\python.exe src\app\main_os.py
```

O banco é inicializado pelo aplicativo. Sem configuração prévia de pasta compartilhada ou pasta `banco de dados` em um diretório ancestral, os dados ficam em `src/app/data/`. A configuração persistente no Windows fica em `%LOCALAPPDATA%/Orcamentos_PPP_Enterprise/runtime_config.json`. Uma configuração existente pode direcionar o aplicativo ao banco real: use um perfil de Windows isolado para testes.

## Gerar executáveis

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller pillow
cd src
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm Orcamentos_PPP_Enterprise.spec
..\.venv\Scripts\python.exe -m PyInstaller --noconfirm Orcamentos_PPP_OS.spec
```

Os executáveis são produzidos em `src/dist/`. Os arquivos `.spec` não empacotam o banco de uso local. Cadastre a empresa e seus recursos específicos na instalação de destino. Consulte `README_INSTALACAO_CLIENTE.txt` para orientações da instalação existente.

## Dados e segurança

Este repositório contém código-fonte e recursos do aplicativo. Bancos, backups, relatórios gerados, anexos, documentos operacionais, configurações privadas, arquivos `.env`, executáveis e pacotes de entrega são excluídos pelo `.gitignore`. Logotipos particulares cadastrados na pasta `assets/empresa` também ficam fora do versionamento.

**Limitação existente de autenticação:** a aplicação contém uma conta de recuperação com credencial fixa e armazena senhas sem hash. A rotina de recuperação pode restabelecer a credencial; apenas alterá-la na interface não resolve o problema. Antes de disponibilizar o sistema para uso não controlado, revise a recuperação de acesso e implemente armazenamento seguro de senhas. Recomenda-se manter o repositório privado enquanto essa revisão não for realizada.

O versionamento do código não substitui o backup dos dados operacionais. Preserve o banco real do cliente durante atualizações.

## Verificação desta importação

A preparação para o Git verifica a sintaxe dos arquivos Python e a lista de arquivos versionados. Não constitui teste funcional completo da interface, da geração de documentos ou dos instaladores.

Orcamentos PPP Enterprise - ajuste de segmentos vinculados

Alteracao realizada:
- Na tela Contratos PPP, o campo "Segmentos vinculados" deixou de ser um bloco fixo de checkboxes.
- Agora o campo e uma lista com opcoes marcaveis, facilitando contratos com mais segmentos.
- Foi incluido o botao "Adicionar opcao" para cadastrar novo segmento/linha contratual diretamente pela tela.
- A nova opcao tambem fica disponivel no cadastro de aditivos como "Segmento impactado".

Executaveis finais:
- Orcamentos PPP: C:\Orcamentos_PPP\01_Orcamentos_PPP\Orcamentos_PPP.exe
- OS PPP: C:\Orcamentos_PPP\02_OS_PPP\OS_PPP.exe

Pacote para cliente:
- Pacote_Instalacao_Pendrive_Orcamentos_PPP_20260714

Antes de entregar ou atualizar cliente, consulte:
- README_INSTALACAO_CLIENTE.txt

Validacoes executadas:
- Compilacao de sintaxe de todos os arquivos Python do app.
- Abertura da tela Contratos PPP em modo offscreen.
- Conferencia de lista de segmentos com opcoes marcaveis.
- Build dos dois executaveis com PyInstaller.

Observacao:
- Os textos da interface foram mantidos em UTF-8. Caso o terminal do Windows mostre caracteres estranhos ao ler os arquivos, isso nao significa que a tela esteja gravada errada.
- Se a atualizacao for apenas visual, substitua somente o EXE. Se envolver funcao nova, tela nova, relatorio novo, dependencia ou banco, atualize a pasta completa preservando o app.db real do cliente.

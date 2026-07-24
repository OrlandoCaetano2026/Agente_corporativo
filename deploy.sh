#!/usr/bin/env bash
#
# deploy.sh - Atualiza o repositorio local e publica no GitHub
# Uso: ./deploy.sh  (execute de DENTRO da pasta do repositorio)
#
# Fluxo:
#   1) Verifica se voce esta em um repositorio Git
#   2) Mostra o git status (o que mudou)
#   3) Pede confirmacao (sim/nao)
#   4) Faz add + commit + push
#
# --------------------------------------------------------------------

set -e  # aborta em caso de erro

# --- Cores para melhor leitura ---
VERDE="\033[0;32m"
AMARELO="\033[1;33m"
VERMELHO="\033[0;31m"
AZUL="\033[0;34m"
RESET="\033[0m"

# --- 1) Confirma que estamos dentro de um repo Git ---
if [ ! -d ".git" ]; then
  echo -e "${VERMELHO}[ERRO] Esta pasta nao e um repositorio Git.${RESET}"
  echo -e "       Entre na pasta do projeto (a que tem .git) e rode novamente."
  echo -e "       Dica: use 'cd ~/Agente_corporativo' antes de executar."
  exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo -e "${AZUL}==============================================${RESET}"
echo -e "${AZUL}  DEPLOY -> Branch atual: ${BRANCH}${RESET}"
echo -e "${AZUL}==============================================${RESET}"

# --- 2) Mostra o que mudou ---
echo -e "\n${AMARELO}>> Alteracoes detectadas pelo Git:${RESET}\n"
git status -s

# Se nao houver nada para commitar, encerra
if [ -z "$(git status -s)" ]; then
  echo -e "\n${VERDE}Nada a subir. O repositorio ja esta atualizado. Encerrando.${RESET}"
  exit 0
fi

# --- 3) Confirmacao do usuario ---
echo ""
read -p "$(echo -e "${AMARELO}Deseja subir essas alteracoes para o GitHub? (s/n): ${RESET}")" RESPOSTA

if [[ ! "$RESPOSTA" =~ ^[sSyY]$ ]]; then
  echo -e "${VERMELHO}Operacao cancelada pelo usuario. Nada foi enviado.${RESET}"
  exit 0
fi

# --- 4) Mensagem de commit ---
read -p "$(echo -e "${AZUL}Mensagem do commit (Enter = mensagem padrao): ${RESET}")" MSG
if [ -z "$MSG" ]; then
  MSG="update: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# --- 5) add + commit + push ---
echo -e "\n${AMARELO}>> git add .${RESET}"
git add .

echo -e "${AMARELO}>> git commit${RESET}"
git commit -m "$MSG"

echo -e "${AMARELO}>> git push origin ${BRANCH}${RESET}"
git push origin "$BRANCH"

echo -e "\n${VERDE}==============================================${RESET}"
echo -e "${VERDE}  SUCESSO! Alteracoes publicadas no GitHub.${RESET}"
echo -e "${VERDE}==============================================${RESET}"

ARG NODE_BASE_IMAGE=node:22-bookworm-slim
FROM ${NODE_BASE_IMAGE}

ARG INSTALL_NPM_DEPENDENCIES=1
USER root

WORKDIR /app

COPY package*.json ./

RUN if [ "$INSTALL_NPM_DEPENDENCIES" = "1" ]; then npm ci --omit=dev --no-audit --no-fund; fi

COPY --chown=node:node . .

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000

USER node

CMD ["npm", "start"]

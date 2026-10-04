FROM node:20-slim

# Install pnpm
RUN npm install -g pnpm

WORKDIR /app

COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml* .npmrc* ./

RUN pnpm install

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev"]

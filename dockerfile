FROM node:20-alpine As development

WORKDIR /usr/src/app

COPY package*.json ./

RUN npm install

COPY . .

# Change the CMD to run in development mode
CMD ["npm", "run", "start:dev"]

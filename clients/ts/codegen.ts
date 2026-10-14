import type { CodegenConfig } from "@graphql-codegen/cli";

// Typed documents for clients/operations.graphql, written to graphql/ (`npm run codegen`).
const config: CodegenConfig = {
  schema: "../../contracts/schema.graphql",
  documents: "../operations.graphql",
  generates: {
    "graphql/": {
      preset: "client",
      presetConfig: { fragmentMasking: false },
      config: {
        documentMode: "string", // plain query strings, so sending one needs no GraphQL runtime
        enumsAsTypes: true,
        useTypeImports: true,
        scalars: { Date: "string" },
      },
    },
  },
};

export default config;

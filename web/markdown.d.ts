// Markdown imports as its text (next.config.ts): the landing page reads the eval report's table.
declare module "*.md" {
  const text: string;
  export default text;
}

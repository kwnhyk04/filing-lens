import { AnswerView, ReadAs } from "../../components/answer-view.tsx";
import { DemoBanner, DemoHeader } from "../../components/chrome.tsx";
import { QuoteInView } from "../../components/quote-in-view.tsx";
import { demo } from "../../lib/demo.ts";

export const metadata = { title: "Demo: saved answers" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function DemoPage({ searchParams }: Props) {
  const { offline } = await searchParams;
  return (
    <>
      <DemoHeader page="answers" />
      <main id="main" className="demo">
        <DemoBanner offline={offline === "1"} />
        <h1>Saved answers</h1>
        <p>Questions from the evaluation&apos;s test split, each with its recorded answer and sources.</p>
        <ol className="toc">
          {demo.answers.map((item) => (
            <li key={item.id}>
              <a href={`#q-${item.id}`}>{item.question}</a>
            </li>
          ))}
        </ol>
        {demo.answers.map((item) => (
          <section key={item.id} id={`q-${item.id}`} aria-labelledby={`q-${item.id}-title`} className="saved">
            <h2 id={`q-${item.id}-title`}>{item.question}</h2>
            <ReadAs reading={item.answer.reading} />
            <AnswerView answer={item.answer} sources={demo.sources} prefix={`${item.id}-`} />
          </section>
        ))}
        <QuoteInView />
      </main>
    </>
  );
}

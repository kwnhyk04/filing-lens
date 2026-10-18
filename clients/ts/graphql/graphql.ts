/* eslint-disable */
/** Internal type. DO NOT USE DIRECTLY. */
type Exact<T extends { [key: string]: unknown }> = { [K in keyof T]: T[K] };
/** Internal type. DO NOT USE DIRECTLY. */
export type Incremental<T> = T | { [P in keyof T]?: P extends ' $fragmentName' | '__typename' ? T[P] : never };
import type { DocumentTypeDecoration } from '@graphql-typed-document-node/core';
export type FiscalPeriod =
  | 'FY'
  | 'Q1'
  | 'Q2'
  | 'Q3'
  | 'Q4';

export type FormType =
  | 'FORM_10K'
  | 'FORM_10Q';

export type CompaniesQueryVariables = Exact<{
  first?: number;
  after?: string | null | undefined;
}>;


export type CompaniesQuery = { companies: { edges: Array<{ cursor: string, node: { cik: number, ticker: string, name: string } }>, pageInfo: { hasNextPage: boolean, endCursor: string | null } } };

export type FilingsQueryVariables = Exact<{
  cik?: number | null | undefined;
  formType?: FormType | null | undefined;
  fiscalYear?: number | null | undefined;
  first?: number;
  after?: string | null | undefined;
  chunks?: number;
  facts?: number;
}>;


export type FilingsQuery = { filings: { edges: Array<{ cursor: string, node: { accessionNumber: string, cik: number, formType: FormType, filedOn: string, periodEnd: string, fiscalYear: number, fiscalPeriod: FiscalPeriod, url: string, sections: Array<{ id: string, item: string, title: string }>, chunks: { edges: Array<{ node: { id: string, sectionId: string, text: string } }>, pageInfo: { hasNextPage: boolean, endCursor: string | null } }, facts: { edges: Array<{ node: { id: string, concept: string, label: string, value: number, unit: string, periodStart: string | null, periodEnd: string, fiscalYear: number, fiscalPeriod: FiscalPeriod } }>, pageInfo: { hasNextPage: boolean, endCursor: string | null } } } }>, pageInfo: { hasNextPage: boolean, endCursor: string | null } } };

export type AnswerQueryVariables = Exact<{
  question: string;
  companyIds?: Array<number> | number | null | undefined;
  fiscalYears?: Array<number> | number | null | undefined;
}>;


export type AnswerQuery = { answer: { answer: string, degraded: boolean, refused: boolean, warnings: Array<string>, citations: Array<{ chunkId: string | null, factId: string | null, quote: string, filingUrl: string }>, usage: { inputTokens: number, outputTokens: number, costUsd: number } } };

export type CoverageQueryVariables = Exact<{
  first?: number;
  after?: string | null | undefined;
}>;


export type CoverageQuery = { companies: { pageInfo: { hasNextPage: boolean, endCursor: string | null }, edges: Array<{ node: { cik: number, ticker: string, name: string, filings: { edges: Array<{ node: { accessionNumber: string, formType: FormType, fiscalYear: number, fiscalPeriod: FiscalPeriod, filedOn: string, url: string } }> } } }> } };

export type SourcesQueryVariables = Exact<{
  chunkIds: Array<string | number> | string | number;
  factIds: Array<string | number> | string | number;
}>;


export type SourcesQuery = { chunks: Array<{ id: string, text: string, section: { id: string, item: string, title: string }, filing: { accessionNumber: string, formType: FormType, fiscalYear: number, fiscalPeriod: FiscalPeriod, filedOn: string, url: string, company: { cik: number, ticker: string, name: string } } }>, facts: Array<{ id: string, concept: string, label: string, value: number, unit: string, periodStart: string | null, periodEnd: string, fiscalYear: number, fiscalPeriod: FiscalPeriod, accessionNumber: string, company: { cik: number, ticker: string, name: string } }> };

export class TypedDocumentString<TResult, TVariables>
  extends String
  implements DocumentTypeDecoration<TResult, TVariables>
{
  __apiType?: NonNullable<DocumentTypeDecoration<TResult, TVariables>['__apiType']>;
  private value: string;
  public __meta__?: Record<string, any> | undefined;

  constructor(value: string, __meta__?: Record<string, any> | undefined) {
    super(value);
    this.value = value;
    this.__meta__ = __meta__;
  }

  override toString(): string & DocumentTypeDecoration<TResult, TVariables> {
    return this.value;
  }
}

export const CompaniesDocument = new TypedDocumentString(`
    query Companies($first: Int! = 20, $after: String) {
  companies(first: $first, after: $after) {
    edges {
      cursor
      node {
        cik
        ticker
        name
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
    `) as unknown as TypedDocumentString<CompaniesQuery, CompaniesQueryVariables>;
export const FilingsDocument = new TypedDocumentString(`
    query Filings($cik: Int, $formType: FormType, $fiscalYear: Int, $first: Int! = 20, $after: String, $chunks: Int! = 5, $facts: Int! = 5) {
  filings(
    cik: $cik
    formType: $formType
    fiscalYear: $fiscalYear
    first: $first
    after: $after
  ) {
    edges {
      cursor
      node {
        accessionNumber
        cik
        formType
        filedOn
        periodEnd
        fiscalYear
        fiscalPeriod
        url
        sections {
          id
          item
          title
        }
        chunks(first: $chunks) {
          edges {
            node {
              id
              sectionId
              text
            }
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
        facts(first: $facts) {
          edges {
            node {
              id
              concept
              label
              value
              unit
              periodStart
              periodEnd
              fiscalYear
              fiscalPeriod
            }
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
    `) as unknown as TypedDocumentString<FilingsQuery, FilingsQueryVariables>;
export const AnswerDocument = new TypedDocumentString(`
    query Answer($question: String!, $companyIds: [Int!], $fiscalYears: [Int!]) {
  answer(question: $question, companyIds: $companyIds, fiscalYears: $fiscalYears) {
    answer
    degraded
    citations {
      chunkId
      factId
      quote
      filingUrl
    }
    usage {
      inputTokens
      outputTokens
      costUsd
    }
    refused
    warnings
  }
}
    `) as unknown as TypedDocumentString<AnswerQuery, AnswerQueryVariables>;
export const CoverageDocument = new TypedDocumentString(`
    query Coverage($first: Int! = 20, $after: String) {
  companies(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        cik
        ticker
        name
        filings(first: 5) {
          edges {
            node {
              accessionNumber
              formType
              fiscalYear
              fiscalPeriod
              filedOn
              url
            }
          }
        }
      }
    }
  }
}
    `) as unknown as TypedDocumentString<CoverageQuery, CoverageQueryVariables>;
export const SourcesDocument = new TypedDocumentString(`
    query Sources($chunkIds: [ID!]!, $factIds: [ID!]!) {
  chunks(ids: $chunkIds) {
    id
    text
    section {
      id
      item
      title
    }
    filing {
      accessionNumber
      formType
      fiscalYear
      fiscalPeriod
      filedOn
      url
      company {
        cik
        ticker
        name
      }
    }
  }
  facts(ids: $factIds) {
    id
    concept
    label
    value
    unit
    periodStart
    periodEnd
    fiscalYear
    fiscalPeriod
    accessionNumber
    company {
      cik
      ticker
      name
    }
  }
}
    `) as unknown as TypedDocumentString<SourcesQuery, SourcesQueryVariables>;
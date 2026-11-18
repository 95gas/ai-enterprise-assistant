import Navigation from "@/components/ui/custom/navigation"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Route } from "@/lib/types/Route"
import { FileText, ListTree } from "lucide-react"
import { Trans, useLingui } from "@lingui/react/macro"
import { useMemo, useState } from "react"
import { Toggle } from "@/components/ui/toggle"
import { Card, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { StyledMarkdown } from "@/components/ui/custom/styled-markdown"
import GithubSlugger from "github-slugger"

import changelog_it from "@/docs/changelog.it.md?raw"
import changelog_en from "@/docs/changelog.en.md?raw"
import changelog_zh from "@/docs/changelog.zh.md?raw"

type Heading = {
  text: string;
  id: string;
  level: number;
  subItems?: Heading[];
}

const changelogDocs: Record<string, string> = {
  it: changelog_it,
  en: changelog_en,
  zh: changelog_zh
}

const getHeadings = (source: string) => {
  const slugger = new GithubSlugger()
  const headingLines = source.split('\n').filter((line) => line.match(/^#{1,2}\s/))

  return headingLines.reduce((acc: Heading[], raw: string) => {
    const level = raw.match(/^#+/)![0].length
    const text = raw.replace(/^#+\s/, '').trim()
    const id = slugger.slug(text)

    const item: Heading = { text, level, id, subItems: [] }

    if (level === 1) {
      acc.push(item)
    } else if (level === 2 && acc.length > 0) {
      acc[acc.length - 1].subItems?.push(item)
    } else {
      acc.push(item)
    }

    return acc
  }, [])
}

const replaceEnvs = (rawContent: string) => {
  return rawContent.replace(/\${(\w+)}/g, (match, key) => {
    return import.meta.env[key] || match
  })
}

function ChangelogPage() {
  const { i18n } = useLingui()
  const [openIndex, setOpenIndex] = useState(true)
  const rawContent = changelogDocs[i18n.locale] || changelogDocs["en"]
  const content = useMemo(() => replaceEnvs(rawContent), [rawContent])
  const sections = useMemo(() => getHeadings(content), [content])

  const handleScroll = (id: string) => {
    document.getElementById(id)?.scrollIntoView({
      behavior: "smooth",
      block: "start"
    })
  }

  return (
    <div className="w-full flex flex-col h-screen">
      <Navigation>
        <Toggle onClick={() => setOpenIndex(!openIndex)} variant={"outline"} pressed={openIndex}>
          <ListTree className="h-4 w-4 mr-0 md:mr-2" /> 
          <span className="hidden md:block"><Trans id="changelog.index">Index</Trans></span>
        </Toggle>
      </Navigation>
      <main className="h-full overflow-hidden">
        <div className="flex h-full relative">
          <ScrollArea className="w-full h-full">
            <div className="w-full flex justify-center">
              <div className="max-w-[48rem] w-full p-4 grid gap-4">
                <div className="mt-20 mb-20">
                  <StyledMarkdown>{content}</StyledMarkdown>
                </div>
              </div>
            </div>
          </ScrollArea>
          {openIndex && (
            <Card className="w-[calc(100%-2rem)] h-[calc(100%-2rem)] max-w-full m-4 absolute right-0 lg:static lg:max-w-[28rem]">
              <CardHeader>
                <CardTitle><Trans id="changelog.index.title">Changelog Index</Trans></CardTitle>
              </CardHeader>
              <ScrollArea>
                <div className="grid gap-2 p-6 pt-0">
                  {sections.map(section => (
                    <>
                      <div
                        key={section.id}
                        className="text-sm text-muted-foreground cursor-pointer hover:text-foreground"
                        onClick={() => handleScroll(section.id)}
                      >
                        {section.text}
                      </div>
                      <Separator />
                      <ul className="ml-6 list-decimal [&>li:not(:first-child)]:mt-2">
                        {section.subItems?.map(subSection => (
                          <li
                            key={subSection.id}
                            className="text-sm text-muted-foreground cursor-pointer hover:text-foreground"
                            onClick={() => handleScroll(subSection.id)}
                          >
                            {subSection.text}
                          </li>
                        ))}
                      </ul>
                    </>
                  ))}
                </div>
              </ScrollArea>
            </Card>
          )}
        </div>
      </main>
    </div>
  )
}

const ChangelogRoute: Route = {
  path: "changelog",
  element: <ChangelogPage />,
  handle: {
    getPageName: () => <Trans id="changelog.page">Changelog</Trans>,
    getPageSidebar: () => ({
      group: "information",
      icon: <FileText className="h-4 w-4" />
    })
  }
}

export default ChangelogRoute
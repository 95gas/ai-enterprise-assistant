import useAuth from "@/lib/hooks/useAuth"
import { TypographyH4 } from "../ui/typography/h4"
import { Trans } from "@lingui/react/macro"
// import { Card, CardContent, CardHeader, CardTitle } from "../ui/card"
// import { BookOpenText, HelpCircle, PencilLine, Pickaxe } from "lucide-react"

function getFirstName(name: string) {
  if (!name) return "";
  const first = name.split(" ")[0];
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
}

function ChatHeader() {
  const { user } = useAuth()

  return (
    <div className="mt-20 flex flex-col items-center space-y-6 mb-2">
      <img src={"/logo.svg"} alt={import.meta.env.VITE_NAME} className="h-24"/>
      <div className="flex flex-col items-center space-y-2">
        <TypographyH4>
          <Trans>Hello {user?.name ? getFirstName(user.name) : "Guest"}, how can I help you today?</Trans>
        </TypographyH4>
      </div>
      {/* <div className="flex flex-wrap justify-center gap-4">
        <Card className="grow w-52 hover:bg-border cursor-pointer" onClick={() => onClick("Riassumi il seguente documento: ")}>
          <CardHeader>
            <CardTitle className="flex items-center">
              <BookOpenText className="mr-2 mt-1" />
              Riassunto
            </CardTitle>
          </CardHeader>
          <CardContent className="-mt-2 text-muted-foreground">
            Riassumi il seguente documento
          </CardContent>
        </Card>
        <Card className="grow w-52 hover:bg-border cursor-pointer" onClick={() => onClick("In quali documenti posso trovare la risposta alla seguente domanda: ")}>
          <CardHeader>
            <CardTitle className="flex items-center">
              <HelpCircle className="mr-2 mt-1" />
              Domande
            </CardTitle>
          </CardHeader>
          <CardContent className="-mt-2 text-muted-foreground">
            In quali documenti posso trovare la risposta alla seguente domanda
          </CardContent>
        </Card>
        <Card className="grow w-52 hover:bg-border cursor-pointer" onClick={() => onClick("Individua e riporta i dati importanti dal seguente documento: ")}>
          <CardHeader>
            <CardTitle className="flex items-center">
              <Pickaxe className="mr-2 mt-1" />
              Estrazione
            </CardTitle>
          </CardHeader>
          <CardContent className="-mt-2 text-muted-foreground">
            Individua e riporta i dati importanti dal seguente documento
          </CardContent>
        </Card>
        <Card className="grow w-52 hover:bg-border cursor-pointer" onClick={() => onClick("Riscrivi il seguente paragrafo nello stile dei documenti disponibili:\n\n")}>
          <CardHeader>
            <CardTitle className="flex items-center">
              <PencilLine className="mr-2 mt-1" />
              Riscrittura
            </CardTitle>
          </CardHeader>
          <CardContent className="-mt-2 text-muted-foreground">
            Riscrivi il seguente paragrafo nello stile dei documenti disponibili
          </CardContent>
        </Card>
      </div> */}
    </div>
  )
}

export default ChatHeader
import { Model } from "@/lib/types/Model"

async function getModels(): Promise<Model[]> {
  const response = await fetch('/api/general/v0/user_token', {
    method: 'GET',
    credentials: 'same-origin'
  })

  const jsonData = await response.json()
  const models: Model[] = []

  for (const item of jsonData) {
    for (const model of Object.keys(item)) {
      for (const provider of Object.keys(item[model])) {
        models.push({
          model,
          provider,
          ...item[model][provider]
        })
      }
    }
  }

  // TODO: handle errors
  return models
}

export { getModels }

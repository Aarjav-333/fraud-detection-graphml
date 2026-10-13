import client from './client'

export async function getGNNStatus() {
  return (await client.get('/api/gnn/status')).data
}
// GraphSAGE vs GCN on the same test split, from saved evaluation results (no retraining)
export async function getGNNEvaluation(source = 'synthetic') {
  return (await client.get('/api/gnn/evaluation', { params: { source } })).data
}
export async function trainGNN({ source = 'synthetic', model = 'graphsage', epochs = 100 } = {}) {
  // Elliptic download + CPU training can take a while
  return (await client.post('/api/gnn/train', { source, model, epochs }, { timeout: 1800000 })).data
}

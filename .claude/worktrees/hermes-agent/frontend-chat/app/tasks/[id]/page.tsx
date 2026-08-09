import TaskDetailView from '@/components/tasks/TaskDetailView'

export const metadata = { title: 'Task — Decomplica AI' }

export default async function TaskDetailPageRoute({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  return <TaskDetailView taskId={id} />
}

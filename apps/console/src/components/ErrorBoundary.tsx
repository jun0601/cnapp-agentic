import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}
interface State {
  error: Error | null
}

// 최상위 에러 바운더리(진우 권장) — 렌더 중 예외로 화면이 멈추는 걸 막고 복구 UI 제공.
// (네트워크/쿼리 실패는 각 화면의 isError로 처리, 여기선 예상 못 한 렌더 예외를 잡는다.)
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50 p-6 text-center">
          <div className="text-3xl">⚠️</div>
          <h1 className="text-lg font-bold text-slate-800">화면을 표시하는 중 문제가 발생했습니다</h1>
          <p className="max-w-md text-sm text-slate-500">{this.state.error.message}</p>
          <button
            onClick={() => this.setState({ error: null })}
            className="mt-2 rounded bg-slate-900 px-4 py-2 text-sm text-white hover:bg-slate-700"
          >
            다시 시도
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

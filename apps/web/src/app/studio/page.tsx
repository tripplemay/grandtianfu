import { redirect } from 'next/navigation';

// /studio → 项目台。
export default function StudioHome() {
  redirect('/studio/projects');
}

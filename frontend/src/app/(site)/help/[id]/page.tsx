"use client";
import { useParams } from "next/navigation";
import { ArticleView } from "@/components/help/ArticleView";

export default function PublicHelpArticle() { const { id } = useParams<{ id: string }>(); return <ArticleView id={id} mode="public" />; }

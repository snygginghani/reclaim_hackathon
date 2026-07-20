"use client";

import { useMemo, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

/**
 * Curated, dependency-free emoji picker: search + grid, keyboard accessible.
 * Covers the emoji people actually use for page icons; a full picker can swap
 * in behind the same props without touching call sites.
 */
const EMOJI: [string, string][] = [
  ["📄", "page document file"], ["📝", "memo note write"], ["📚", "books library study"],
  ["📖", "book read"], ["✏️", "pencil edit"], ["🖊️", "pen write"], ["📌", "pin important"],
  ["📍", "location pin"], ["🔖", "bookmark tag"], ["🗂️", "folders organize"],
  ["📁", "folder"], ["🗃️", "archive box"], ["📊", "chart bar analytics"],
  ["📈", "chart growth up"], ["📉", "chart down"], ["🧮", "abacus calculate"],
  ["💡", "idea lightbulb"], ["🧠", "brain mind think"], ["🎯", "target goal dart"],
  ["🚀", "rocket launch ship"], ["🔥", "fire hot streak"], ["⭐", "star favorite"],
  ["✨", "sparkles magic new"], ["⚡", "lightning fast bolt"], ["🌟", "glowing star"],
  ["✅", "check done complete"], ["☑️", "checkbox task"], ["📋", "clipboard tasks"],
  ["🗓️", "calendar schedule"], ["📅", "calendar date"], ["⏰", "alarm clock time"],
  ["⌛", "hourglass time"], ["🏠", "home house"], ["🏢", "office building company"],
  ["🏗️", "construction building"], ["🛠️", "tools build"], ["🔧", "wrench fix"],
  ["⚙️", "gear settings"], ["🔬", "microscope research science"], ["🧪", "test tube experiment"],
  ["🔭", "telescope explore"], ["🧬", "dna biology"], ["💻", "laptop computer code"],
  ["🖥️", "desktop computer"], ["📱", "phone mobile"], ["🌐", "globe web world"],
  ["🔒", "lock secure private"], ["🔑", "key access"], ["🛡️", "shield security"],
  ["💰", "money bag finance"], ["💵", "dollar cash"], ["💳", "credit card payment"],
  ["🛒", "shopping cart"], ["📦", "package box product"], ["✈️", "airplane travel"],
  ["🗺️", "map travel"], ["🌍", "earth globe"], ["🏔️", "mountain adventure"],
  ["🏖️", "beach vacation"], ["🎨", "art palette design"], ["🎭", "theater drama"],
  ["🎵", "music note"], ["🎬", "movie film clapper"], ["📷", "camera photo"],
  ["🎮", "game controller"], ["🏀", "basketball sport"], ["⚽", "soccer football"],
  ["🏋️", "gym workout fitness"], ["🧘", "yoga meditation"], ["🍎", "apple food fruit"],
  ["🍕", "pizza food"], ["☕", "coffee cafe"], ["🍽️", "meal restaurant food"],
  ["🌱", "seedling plant grow"], ["🌳", "tree nature"], ["🌸", "blossom flower"],
  ["🌈", "rainbow"], ["☀️", "sun sunny"], ["🌙", "moon night"], ["❤️", "heart love red"],
  ["💜", "purple heart"], ["💙", "blue heart"], ["🧡", "orange heart"],
  ["🎁", "gift present"], ["🎉", "party celebrate confetti"], ["🏆", "trophy win award"],
  ["🥇", "gold medal first"], ["👥", "people team users"], ["🤝", "handshake deal partner"],
  ["👋", "wave hello"], ["💬", "speech chat message"], ["📣", "megaphone announce"],
  ["📧", "email mail"], ["🧭", "compass navigate"], ["♻️", "recycle sustainability"],
  ["🐛", "bug insect issue"], ["🦄", "unicorn"], ["🐶", "dog puppy pet"],
  ["🐱", "cat kitten pet"], ["🤖", "robot ai bot"], ["👾", "alien game pixel"],
  ["🧸", "teddy bear kids"], ["⚖️", "law balance legal"], ["🩺", "health medical doctor"],
  ["💊", "pill medicine"], ["🎓", "graduation education learn"], ["🏫", "school education"],
  ["🔔", "bell notification"], ["🚧", "construction wip barrier"], ["🗑️", "trash delete bin"],
  ["🧾", "receipt invoice"], ["✍️", "writing hand sign"], ["🪄", "magic wand"],
];

export function EmojiPicker({
  value,
  onSelect,
  children,
}: {
  value: string | null;
  onSelect: (emoji: string | null) => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? EMOJI.filter(([, names]) => names.includes(q)) : EMOJI;
  }, [query]);

  return (
    <Popover
      open={open}
      onOpenChange={(v: boolean) => {
        setOpen(v);
        if (!v) setQuery("");
      }}
    >
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent className="w-72 p-2" align="start">
        <div className="mb-2 flex items-center gap-2">
          <Input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search emoji…"
            aria-label="Search emoji"
            className="h-8"
          />
          {value && (
            <Button
              variant="ghost"
              size="sm"
              className="h-8 shrink-0 text-muted-foreground"
              onClick={() => {
                onSelect(null);
                setOpen(false);
              }}
            >
              Remove
            </Button>
          )}
        </div>
        <div role="listbox" aria-label="Emoji" className="grid max-h-56 grid-cols-8 gap-0.5 overflow-y-auto">
          {filtered.map(([emoji, names]) => (
            <button
              key={emoji}
              role="option"
              aria-selected={value === emoji}
              aria-label={names.split(" ")[0]}
              onClick={() => {
                onSelect(emoji);
                setOpen(false);
              }}
              className="flex size-8 items-center justify-center rounded-md text-lg hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring"
            >
              {emoji}
            </button>
          ))}
          {filtered.length === 0 && (
            <p className="col-span-8 py-6 text-center text-sm text-muted-foreground">
              No matches — try “idea”, “book”, “rocket”…
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { listGodowns, type Godown } from "../features/stock/api";
import { listBranches, type Branch } from "../features/users/api";
import { useAuth } from "../store/auth";

/** The branch a screen is working in, and the godowns that go with it.
 *
 * Branch is the visibility boundary as of V2.16, so nearly every screen needs
 * the same three things: which branches this user may work in, which one is
 * selected, and the godowns belonging to it. Having each page re-derive that
 * is how Stock, Purchase and Transfers ended up offering godowns from branches
 * the document could never post to.
 */
export function useBranchScope() {
  const { user: me } = useAuth();
  const allBranches = useQuery({ queryKey: ["branches"], queryFn: listBranches });
  const allGodowns = useQuery({ queryKey: ["godowns", "all"], queryFn: () => listGodowns(true) });

  // RLS already hides other branches, but a super user with several still gets
  // a list — and the picker must never offer one the server would refuse.
  const branches: Branch[] = useMemo(
    () => (allBranches.data ?? []).filter((b) => me?.branch_ids.includes(b.id)),
    [allBranches.data, me],
  );

  const [branch, setBranch] = useState("");
  useEffect(() => {
    if (branches.length && !branch) setBranch(String(branches[0].id));
  }, [branches, branch]);

  const godowns: Godown[] = useMemo(
    () => (allGodowns.data ?? []).filter((g) => String(g.branch_id) === branch),
    [allGodowns.data, branch],
  );

  const branchName = (id: number) =>
    (allBranches.data ?? []).find((b) => b.id === id)?.name ?? `#${id}`;

  return {
    branch,
    setBranch,
    branchId: branch ? Number(branch) : undefined,
    branches,
    godowns,
    branchName,
    /** more than one branch to choose between — otherwise the picker is noise */
    multiBranch: branches.length > 1,
  };
}

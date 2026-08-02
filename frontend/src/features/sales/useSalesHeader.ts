import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../store/auth";
import { listAccounts, listPaymentTypes } from "../accounts/api";
import { listParties } from "../parties/api";
import { listGodowns } from "../stock/api";
import { listBranches } from "../users/api";

/** The customer/branch header every sales document shares, plus the lists it
 *  needs. Split out so the order, invoice and return screens agree on how a
 *  branch narrows the godowns rather than each re-deriving it. */
export function useSalesHeader() {
  const { user: me } = useAuth();
  const parties = useQuery({ queryKey: ["parties"], queryFn: () => listParties() });
  const allGodowns = useQuery({ queryKey: ["godowns", "all"], queryFn: () => listGodowns(true) });
  const allBranches = useQuery({ queryKey: ["branches"], queryFn: listBranches });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });
  const paymentTypes = useQuery({ queryKey: ["payment-types"], queryFn: () => listPaymentTypes() });

  const [customer, setCustomer] = useState("");
  const [branch, setBranch] = useState("");

  // only branches this user may post into — the server refuses the rest
  const branches = useMemo(
    () => (allBranches.data ?? []).filter((b) => me?.branch_ids.includes(b.id)),
    [allBranches.data, me],
  );

  useEffect(() => {
    if (parties.data?.length && !customer) setCustomer(String(parties.data[0].id));
    if (branches.length && !branch) setBranch(String(branches[0].id));
  }, [parties.data, branches, customer, branch]);

  // a document ships out of its own branch's godowns and no others
  const godowns = useMemo(
    () => (allGodowns.data ?? []).filter((g) => String(g.branch_id) === branch),
    [allGodowns.data, branch],
  );

  const partyName = (id: number) => parties.data?.find((p) => p.id === id)?.name ?? String(id);

  return {
    customer, setCustomer,
    branch, setBranch,
    parties: parties.data ?? [],
    branches,
    godowns,
    accounts: accounts.data ?? [],
    paymentTypes: paymentTypes.data ?? [],
    partyName,
  };
}

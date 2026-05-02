/**
 * Module augmentation for `tabulator-tables` 6.x. The DefinitelyTyped
 * package (@types/tabulator-tables) trails the runtime API for a few
 * options we rely on. Add only what we actually use.
 */

import "tabulator-tables";

declare module "tabulator-tables" {
  interface ColumnDefinition {
    headerClass?: string;
  }

  interface Options {
    cssClass?: string;
  }
}

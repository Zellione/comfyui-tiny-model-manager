import { Component, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MODEL_TYPES, ModelType } from '../../utils/model-types';

/**
 * A `<select>` listing every model type. Mirrors the `[ngModel]`/`(ngModelChange)`
 * pattern via `[value]`/`(valueChange)` so callers backed by functional getters/setters
 * (e.g. per-row maps) bind exactly as the inline selects did. `:host { display: contents }`
 * keeps it layout-transparent so surrounding flex/grid styling is unaffected.
 */
@Component({
  selector: 'app-model-type-select',
  imports: [FormsModule],
  template: `
    <select [ngModel]="value()" (ngModelChange)="valueChange.emit($event)">
      @for (t of modelTypes; track t) {
        <option [value]="t">{{ t }}</option>
      }
    </select>
  `,
  styles: `
    :host {
      display: contents;
    }
  `,
})
export class ModelTypeSelect {
  value = input<ModelType>('checkpoints');
  valueChange = output<ModelType>();
  modelTypes = MODEL_TYPES;
}

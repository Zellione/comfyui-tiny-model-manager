import { TranslateLoader, TranslationObject, provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';
import enTranslations from '../../public/i18n/en.json';

class StaticTranslateLoader implements TranslateLoader {
  getTranslation(): ReturnType<TranslateLoader['getTranslation']> {
    return of(enTranslations as TranslationObject);
  }
}

export function provideTranslateServiceForTests() {
  return provideTranslateService({
    lang: 'en',
    loader: { provide: TranslateLoader, useClass: StaticTranslateLoader },
  });
}

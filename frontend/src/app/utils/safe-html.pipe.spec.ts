import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { SafeHtmlPipe } from './safe-html.pipe';

describe('SafeHtmlPipe', () => {
  let pipe: SafeHtmlPipe;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    pipe = TestBed.runInInjectionContext(() => new SafeHtmlPipe(TestBed.inject(DomSanitizer)));
  });

  it('passes safe HTML through', () => {
    const result = pipe.transform('<p>Hello <strong>world</strong></p>') as {
      changingThisBreaksApplicationSecurity: string;
    };
    expect(result.changingThisBreaksApplicationSecurity).toContain('Hello');
    expect(result.changingThisBreaksApplicationSecurity).toContain('<strong>');
  });

  it('strips script tags', () => {
    const result = pipe.transform('<p>Hi</p><script>alert(1)</script>') as {
      changingThisBreaksApplicationSecurity: string;
    };
    expect(result.changingThisBreaksApplicationSecurity).not.toContain('<script>');
    expect(result.changingThisBreaksApplicationSecurity).not.toContain('alert');
  });

  it('strips on* event handlers', () => {
    const result = pipe.transform('<img src="x" onerror="alert(1)">') as {
      changingThisBreaksApplicationSecurity: string;
    };
    expect(result.changingThisBreaksApplicationSecurity).not.toContain('onerror');
  });

  it('strips javascript: hrefs', () => {
    const result = pipe.transform('<a href="javascript:alert(1)">click</a>') as {
      changingThisBreaksApplicationSecurity: string;
    };
    expect(result.changingThisBreaksApplicationSecurity).not.toContain('javascript:');
  });

  it('handles null/undefined gracefully', () => {
    expect(() => pipe.transform(null)).not.toThrow();
    expect(() => pipe.transform(undefined)).not.toThrow();
  });
});

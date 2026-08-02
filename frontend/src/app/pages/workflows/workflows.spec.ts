import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { provideTranslateServiceForTests } from '../../../test-helpers/translate-testing';
import { Workflows } from './workflows';
import { WorkflowStoreService } from '../../services/workflow-store';
import { NotificationService } from '../../services/notification';
import { TagService } from '../../services/tags';

const mockStore = {
  search: vi.fn().mockReturnValue(of({ items: [], metadata: {}, installed_version_ids: [] })),
  download: vi.fn(),
  list: vi.fn().mockReturnValue(of([])),
  deleteEntry: vi.fn(),
  exportWorkflow: vi.fn(),
  openInComfy: vi.fn(),
  fileUrl: vi.fn(),
};

async function createFixture() {
  await TestBed.configureTestingModule({
    imports: [Workflows],
    providers: [
      { provide: WorkflowStoreService, useValue: mockStore },
      { provide: NotificationService, useValue: { show: vi.fn() } },
      { provide: TagService, useValue: { searchTags: vi.fn().mockReturnValue(of([])) } },
      provideTranslateServiceForTests(),
    ],
  }).compileComponents();
  return TestBed.createComponent(Workflows);
}

describe('Workflows', () => {
  beforeEach(() => vi.clearAllMocks());

  it('opens on the browse tab', async () => {
    const fixture = await createFixture();
    expect(fixture.componentInstance.activeTab()).toBe('browse');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-workflows-browse')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('app-workflows-installed')).toBeNull();
  });

  it('switches to the installed tab', async () => {
    const fixture = await createFixture();
    fixture.componentInstance.activeTab.set('installed');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('app-workflows-installed')).toBeTruthy();
    expect(fixture.nativeElement.querySelector('app-workflows-browse')).toBeNull();
  });
});
